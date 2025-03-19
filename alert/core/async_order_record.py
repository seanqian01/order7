import logging
import threading
from datetime import datetime
from django.db import transaction
from alert.core.async_db import async_db_handler
from alert.models import OrderRecord
from alert.trade.hyper_order import HyperliquidTrader
from decimal import Decimal

logger = logging.getLogger(__name__)

def mask_sensitive_info(text, show_chars=4):
    """
    隐藏敏感信息，只显示前几个和后几个字符
    
    :param text: 需要隐藏的文本
    :param show_chars: 前后各显示的字符数
    :return: 隐藏后的文本
    """
    if not text or len(text) <= show_chars * 2:
        return text
    
    return f"{text[:show_chars]}...{text[-show_chars:]}"

def update_order_details_async(order_record_id):
    """
    异步更新订单详细信息
    
    :param order_record_id: OrderRecord的ID
    """
    try:
        # 获取订单记录
        order_record = OrderRecord.objects.get(id=order_record_id)
        logger.info(f"开始异步更新订单详情: order_id={order_record.order_id}, symbol={order_record.symbol}")
        
        # 如果订单已经是取消状态，直接跳过后续处理
        if order_record.status == 'CANCELLED':
            logger.info(f"订单 {order_record.order_id} 已取消，无需更新详情")
            return
        
        # 获取订单详情
        trader = HyperliquidTrader()
        
        # 先查询最新的订单状态
        try:
            latest_status = trader.get_order_status(order_record.symbol, order_record.cloid)  # 使用交易所订单号查询
            if latest_status and latest_status["status"] == "success":
                current_status = latest_status.get("order_status")
                logger.info(f"订单 {order_record.order_id}(交易所订单号: {order_record.cloid}) 当前状态: {current_status}")
                
                # 如果订单已取消，跳过更新
                if current_status == "CANCELED":
                    logger.info(f"订单 {order_record.order_id} 已取消，无需更新详情")
                    return
                
                # 如果API返回的状态是FILLED或PARTIALLY_FILLED，更新数据库中的状态
                if current_status in ["FILLED", "PARTIALLY_FILLED"] and order_record.status != current_status:
                    logger.info(f"更新订单状态: {order_record.status} -> {current_status}")
                    order_record.status = current_status
                    
                    # 如果API返回了成交数量，也更新它
                    if "filled_quantity" in latest_status:
                        order_record.filled_quantity = latest_status["filled_quantity"]
                        logger.info(f"从API状态更新成交数量: {latest_status['filled_quantity']}")
                    
                    # 如果API返回了实际成交价格，更新filled_price字段
                    if "price" in latest_status and latest_status["price"] is not None:
                        actual_price = Decimal(str(latest_status["price"]))
                        # 更新成交价格字段
                        if order_record.filled_price != actual_price:
                            logger.info(f"更新订单实际成交价格: {order_record.filled_price} -> {actual_price}")
                            order_record.filled_price = actual_price
                        else:
                            logger.info(f"订单实际成交价格无变化: {order_record.filled_price}")
        except Exception as e:
            logger.warning(f"查询订单 {order_record.order_id} 最新状态时出错: {str(e)}，将继续使用数据库中的状态")
        
        # 获取订单详细信息
        order_details = get_order_details(trader, order_record.symbol, order_record.cloid, order_record.status)  # 使用交易所订单号查询
        
        if order_details and order_details["status"] == "success":
            # 检查是否获取到了关键字段
            has_key_fields = False
            missing_fields = []
            
            # 检查fee字段
            if "fee" in order_details and order_details["fee"] is not None:
                has_key_fields = True
                order_record.fee = Decimal(str(order_details["fee"]))
                logger.info(f"获取到订单手续费: {order_details['fee']}")
            else:
                missing_fields.append("fee")
            
            # 检查filled_quantity字段
            if "filled_quantity" in order_details and order_details["filled_quantity"] is not None:
                has_key_fields = True
                # 只有当API返回的成交数量与当前记录不同时才更新
                if order_record.filled_quantity != order_details["filled_quantity"]:
                    logger.info(f"更新订单已成交数量: {order_record.filled_quantity} -> {order_details['filled_quantity']}")
                    order_record.filled_quantity = order_details["filled_quantity"]
                else:
                    logger.info(f"订单已成交数量无变化: {order_record.filled_quantity}")
            else:
                missing_fields.append("filled_quantity")
            
            # 检查filled_time字段
            if "filled_time" in order_details and order_details["filled_time"] is not None:
                has_key_fields = True
                
                # 将毫秒时间戳转换为datetime对象
                try:
                    # 确保filled_time是毫秒级时间戳
                    if isinstance(order_details["filled_time"], datetime):
                        # 已经是datetime对象
                        order_record.filled_time = order_details["filled_time"]
                        logger.info(f"获取到订单成交时间: {order_details['filled_time']}")
                    elif order_details["filled_time"] > 10000000000:  # 判断是否为毫秒时间戳
                        # 将毫秒转换为秒
                        seconds_timestamp = order_details["filled_time"] / 1000
                        # 转换为datetime对象
                        filled_datetime = datetime.fromtimestamp(seconds_timestamp)
                        order_record.filled_time = filled_datetime
                        logger.info(f"获取到订单成交时间戳(毫秒转datetime): {order_details['filled_time']} -> {filled_datetime}")
                    else:
                        # 已经是秒级时间戳
                        filled_datetime = datetime.fromtimestamp(order_details["filled_time"])
                        order_record.filled_time = filled_datetime
                        logger.info(f"获取到订单成交时间戳(秒转datetime): {order_details['filled_time']} -> {filled_datetime}")
                except Exception as e:
                    logger.error(f"转换filled_time时出错: {str(e)}")
                    missing_fields.append("filled_time")
                    has_key_fields = len(missing_fields) < 3  # 如果只有filled_time出错，仍然保存其他字段
            else:
                missing_fields.append("filled_time")
            
            # 检查filled_price字段
            if "filled_price" in order_details and order_details["filled_price"] is not None:
                has_key_fields = True
                # 只有当API返回的成交价格与当前记录不同时才更新
                if order_record.filled_price != order_details["filled_price"]:
                    logger.info(f"更新订单实际成交价格: {order_record.filled_price} -> {order_details['filled_price']}")
                    order_record.filled_price = order_details["filled_price"]
                else:
                    logger.info(f"订单实际成交价格无变化: {order_record.filled_price}")
            else:
                missing_fields.append("filled_price")
            
            # 设置订单类型
            if order_record.is_stop_loss:
                # 如果是止损单，直接设置为平仓单
                order_record.order_type = "CLOSE"
                logger.info(f"设置止损单订单类型为平仓单: {order_record.order_type}")
            else:
                # 非止损单，根据reduce_only标志设置
                order_record.order_type = "CLOSE" if order_record.reduce_only else "OPEN"
                logger.info(f"设置普通订单类型: {order_record.order_type}")
            
            # 只有在获取到至少一个关键字段时才保存
            if has_key_fields:
                # 异步保存
                try:
                    async_db_handler.async_save(order_record)
                    logger.info(f"订单 {order_record.order_id} 详细信息已异步更新")
                except Exception as e:
                    logger.error(f"保存订单记录时出错: {str(e)}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    
                    # 尝试使用原始SQL更新
                    try:
                        from django.db import connection
                        with connection.cursor() as cursor:
                            # 构建更新SQL
                            update_fields = []
                            params = []
                            
                            if "fee" in order_details and order_details["fee"] is not None:
                                update_fields.append("fee = %s")
                                params.append(float(order_details["fee"]))
                            
                            if "filled_quantity" in order_details and order_details["filled_quantity"] is not None:
                                update_fields.append("filled_quantity = %s")
                                params.append(float(order_details["filled_quantity"]))
                            
                            # 对于filled_time，直接使用NULL，避免类型转换问题
                            if "filled_time" in order_details and order_details["filled_time"] is not None:
                                update_fields.append("filled_time = NULL")
                            
                            # 更新order_type
                            update_fields.append("order_type = %s")
                            if order_record.is_stop_loss:
                                params.append("CLOSE")
                            else:
                                params.append("CLOSE" if order_record.reduce_only else "OPEN")
                            
                            # 如果有实际成交价格，更新filled_price字段
                            if "filled_price" in order_details and order_details["filled_price"] is not None:
                                update_fields.append("filled_price = %s")
                                params.append(float(order_details["filled_price"]))
                            
                            if update_fields:
                                sql = f"UPDATE order_record SET {', '.join(update_fields)} WHERE id = %s"
                                params.append(order_record_id)
                                cursor.execute(sql, params)
                                logger.info(f"使用原始SQL更新订单记录成功: {sql} {params}")
                    except Exception as e2:
                        logger.error(f"使用原始SQL更新订单记录时出错: {str(e2)}")
            else:
                logger.warning(f"订单 {order_record.order_id} 未获取到任何关键字段 (缺失: {', '.join(missing_fields)})，不保存更新")
        else:
            error_msg = order_details.get("error", "未知错误") if order_details else "获取订单详情失败"
            logger.warning(f"获取订单 {order_record.order_id} 详情失败: {error_msg}")
    
    except OrderRecord.DoesNotExist:
        logger.error(f"订单记录不存在: id={order_record_id}")
    except Exception as e:
        logger.error(f"更新订单详情时出错: {str(e)}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")


def get_order_details(trader, symbol, cloid, order_status):
    """
    获取订单详细信息，包括手续费、成交数量、成交时间等
    
    该函数使用 query_order_by_cloid 方法直接查询订单状态，避免不必要的历史成交记录查询。
    对于已成交的订单，会从订单状态中提取成交价格、数量和时间信息，
    仅在需要获取手续费时才会查询历史成交记录。
    
    :param trader: 交易对象
    :param symbol: 交易对符号
    :param cloid: 交易所的订单号（从API的cloid字段获取）
    :param order_status: 订单状态
    :return: 订单详细信息字典，包含 status、fee、filled_quantity、filled_time 等字段
    """
    try:
        logger.info(f"获取订单详情: symbol={symbol}, cloid={cloid}, order_status={order_status}")
        
        # 如果订单已取消，直接返回空信息
        if order_status == "CANCELED":
            logger.info(f"订单 {cloid} 已取消，返回空信息")
            return {
                "status": "success",
                "fee": Decimal('0'),
                "filled_quantity": None,
                "filled_time": None,
                "source": "cancelled_order"
            }
        
        # 优先使用query_order_by_cloid方法获取订单状态
        from hyperliquid.utils.types import Cloid
        try:
            logger.debug(f"尝试将cloid转换为Cloid对象: {cloid}")
            # 直接使用传入的cloid创建Cloid对象
            cloid_obj = Cloid.from_str(str(cloid))
            logger.debug(f"成功将cloid转换为Cloid对象: {cloid_obj}")
            
            # 查询订单状态
            logger.debug(f"调用API查询订单状态: wallet_address={mask_sensitive_info(trader.wallet_address)}, cloid={cloid_obj}")
            order_status_result = trader.info.query_order_by_cloid(trader.wallet_address, cloid_obj)
            logger.debug(f"订单详细信息查询结果: {order_status_result}")
            
            # 检查订单状态结果是否包含 order 字段
            if order_status_result and order_status_result.get('status') == 'order' and order_status_result.get('order'):
                order_info = order_status_result['order']
                logger.debug(f"解析订单状态: {order_info}")
                
                # 解析订单详细信息
                result = {"status": "success", "source": "query_order_by_cloid"}
                
                # 获取订单状态
                order_status_str = order_info.get('status', '')
                order_data = order_info.get('order', {})
                
                # 如果订单已成交
                if order_status_str == 'filled':
                    # 获取订单数量
                    orig_size = float(order_data.get('origSz', 0))
                    result["filled_quantity"] = orig_size
                    logger.info(f"成功获取已成交订单的数量: {result['filled_quantity']}")
                    
                    # 获取成交时间
                    # API返回的order.timestamp是订单创建时间，而应该使用statusTimestamp作为状态更新时间
                    # 对于已成交的订单，statusTimestamp就是成交时间
                    status_timestamp_ms = int(order_info.get('statusTimestamp', 0))
                    if status_timestamp_ms > 0:
                        # 将毫秒时间戳转换为秒
                        seconds_timestamp = status_timestamp_ms / 1000
                        # 转换为datetime对象
                        filled_datetime = datetime.fromtimestamp(seconds_timestamp)
                        result["filled_time"] = filled_datetime
                        logger.info(f"成功获取已成交订单的成交时间: {result['filled_time']}")
                    else:
                        # 如果没有statusTimestamp，使用当前时间作为备选
                        filled_datetime = datetime.now()
                        result["filled_time"] = filled_datetime
                        logger.info(f"未找到statusTimestamp，设置已成交订单的成交时间为当前时间: {result['filled_time']}")
                    
                    # 获取成交价格
                    if "limitPx" in order_data:
                        result["filled_price"] = Decimal(str(order_data["limitPx"]))
                        logger.info(f"成功获取已成交订单的成交价格: {result['filled_price']}")
                    
                    # 在订单状态中手续费信息通常不存在，设置默认值
                    result["fee"] = Decimal('0')
                    logger.info(f"使用默认手续费值: {result['fee']}")
                    
                    # 如果订单数据中包含fee字段（不太可能），则使用它
                    if "fee" in order_data:
                        result["fee"] = Decimal(str(order_data["fee"]))
                        logger.info(f"从订单状态中获取到手续费: {result['fee']}")
                    
                    # 如果需要手续费的精确值，可以在订单成交后通过其他方式更新
                    # 例如，可以通过定期任务或其他方式获取手续费并更新订单记录
                    
                    return result
                
                # 如果订单部分成交，获取部分成交信息
                elif order_status_str == 'partial_fill':
                    # 如果有部分成交信息
                    if "sz" in order_data:
                        result["filled_quantity"] = float(order_data["sz"])
                        logger.info(f"成功获取部分成交订单的数量: {result['filled_quantity']}")
                    
                    # 在订单状态中手续费信息通常不存在，设置默认值
                    result["fee"] = Decimal('0')
                    logger.info(f"使用默认手续费值: {result['fee']}")
                    
                    # 如果订单数据中包含fee字段（不太可能），则使用它
                    if "fee" in order_data:
                        result["fee"] = Decimal(str(order_data["fee"]))
                        logger.info(f"从订单状态中获取到手续费: {result['fee']}")
                    
                    # 如果需要手续费的精确值，可以在订单成交后通过其他方式更新
                    # 例如，可以通过定期任务或其他方式获取手续费并更新订单记录
                    
                    # 获取成交时间
                    # 对于部分成交的订单，也使用statusTimestamp作为成交时间
                    status_timestamp_ms = int(order_info.get('statusTimestamp', 0))
                    if status_timestamp_ms > 0:
                        # 将毫秒时间戳转换为秒
                        seconds_timestamp = status_timestamp_ms / 1000
                        # 转换为datetime对象
                        filled_datetime = datetime.fromtimestamp(seconds_timestamp)
                        result["filled_time"] = filled_datetime
                        logger.info(f"成功获取部分成交订单的成交时间: {result['filled_time']}")
                    else:
                        # 如果没有statusTimestamp，使用当前时间作为备选
                        filled_datetime = datetime.now()
                        result["filled_time"] = filled_datetime
                        logger.info(f"未找到statusTimestamp，设置部分成交订单的成交时间为当前时间: {result['filled_time']}")
                    
                    # 获取成交价格
                    if "limitPx" in order_data:
                        result["filled_price"] = Decimal(str(order_data["limitPx"]))
                        logger.info(f"成功获取部分成交订单的成交价格: {result['filled_price']}")
                
                return result
            
            # 如果查询结果为空或没有有效信息，返回错误
            logger.info(f"通过query_order_by_cloid未获取到有效信息")
            return {"status": "error", "error": "未能获取订单状态信息"}
            
        except Exception as e:
            logger.error(f"使用query_order_by_cloid方法查询订单状态时出错: {str(e)}")
            return {"status": "error", "error": f"查询订单状态时出错: {str(e)}"}
    
    except Exception as e:
        logger.error(f"获取订单详情时出错: {str(e)}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return {"status": "error", "error": f"获取订单详情时出错: {str(e)}"}





def manually_update_order_details(order_record_id):
    """
    手动更新订单详细信息，用于管理界面的手动触发
    
    :param order_record_id: OrderRecord的ID
    :return: 包含更新状态和消息的字典
    """
    try:
        logger.info(f"开始手动更新订单详情: order_record_id={order_record_id}")
        
        # 获取订单记录
        order_record = OrderRecord.objects.get(id=order_record_id)
        logger.debug(f"获取到订单记录: order_id={order_record.order_id}, symbol={order_record.symbol}, status={order_record.status}")
        
        # 获取订单详情
        trader = HyperliquidTrader()
        order_details = get_order_details(trader, order_record.symbol, order_record.cloid, order_record.status)  # 使用交易所订单号查询
        
        if order_details and order_details["status"] == "success":
            # 记录更新前的值
            old_values = {
                "order_id": order_record.order_id,  # 我们系统的订单号
                "cloid": order_record.cloid,      # 交易所的订单号
                "fee": order_record.fee,
                "filled_time": order_record.filled_time,
                "order_type": order_record.order_type,
                "filled_price": order_record.filled_price,
                "filled_quantity": order_record.filled_quantity
            }
            
            # 检查是否有必要的字段
            has_updates = False
            updates = []
            
            # 更新订单记录
            if "cloid" in order_details and order_details["cloid"] is not None and order_record.cloid != order_details["cloid"]:
                order_record.cloid = str(order_details["cloid"])  # 更新交易所订单号
                has_updates = True
                updates.append(f"交易所订单号: {mask_sensitive_info(old_values['cloid'])} -> {mask_sensitive_info(order_details['cloid'])}")
                logger.info(f"更新交易所订单号: {mask_sensitive_info(old_values['cloid'])} -> {mask_sensitive_info(order_details['cloid'])}")
            
            if "fee" in order_details and order_details["fee"] is not None and order_record.fee != order_details["fee"]:
                order_record.fee = Decimal(str(order_details["fee"]))
                has_updates = True
                updates.append(f"手续费: {old_values['fee']} -> {order_details['fee']}")
                logger.info(f"更新订单手续费: {old_values['fee']} -> {order_details['fee']}")
            
            if "filled_quantity" in order_details and order_details["filled_quantity"] is not None and order_record.filled_quantity != order_details["filled_quantity"]:
                order_record.filled_quantity = order_details["filled_quantity"]
                has_updates = True
                updates.append(f"已成交数量: {old_values.get('filled_quantity', 0)} -> {order_details['filled_quantity']}")
                logger.info(f"更新订单已成交数量: {old_values.get('filled_quantity', 0)} -> {order_details['filled_quantity']}")
            
            if "filled_time" in order_details and order_details["filled_time"] is not None:
                # 将毫秒时间戳转换为datetime对象
                try:
                    # 确保filled_time是毫秒级时间戳
                    if isinstance(order_details["filled_time"], datetime):
                        # 已经是datetime对象
                        order_record.filled_time = order_details["filled_time"]
                        logger.info(f"获取到订单成交时间: {order_details['filled_time']}")
                    elif order_details["filled_time"] > 10000000000:  # 判断是否为毫秒时间戳
                        # 将毫秒转换为秒
                        seconds_timestamp = order_details["filled_time"] / 1000
                        # 转换为datetime对象
                        filled_datetime = datetime.fromtimestamp(seconds_timestamp)
                        
                        if order_record.filled_time != filled_datetime:
                            order_record.filled_time = filled_datetime
                            has_updates = True
                            updates.append(f"成交时间戳: {old_values['filled_time']} -> {filled_datetime}")
                            logger.info(f"更新订单成交时间戳(毫秒转datetime): {order_details['filled_time']} -> {filled_datetime}")
                    else:
                        # 已经是秒级时间戳
                        filled_datetime = datetime.fromtimestamp(order_details["filled_time"])
                        
                        if order_record.filled_time != filled_datetime:
                            order_record.filled_time = filled_datetime
                            has_updates = True
                            updates.append(f"成交时间戳: {old_values['filled_time']} -> {filled_datetime}")
                            logger.info(f"更新订单成交时间戳(秒转datetime): {order_details['filled_time']} -> {filled_datetime}")
                except Exception as e:
                    logger.error(f"转换filled_time时出错: {str(e)}")
            
            # 判断订单类型（开仓单或平仓单）
            # 无论之前是什么类型，都根据reduce_only标志重新判断
            order_type = "CLOSE" if order_record.reduce_only else "OPEN"
            if order_record.order_type != order_type:
                order_record.order_type = order_type
                has_updates = True
                updates.append(f"订单类型: {old_values['order_type']} -> {order_type}")
                logger.info(f"更新订单类型: {old_values['order_type']} -> {order_type}")
            
            # 如果有更新，保存
            if has_updates:
                try:
                    order_record.save()
                    update_message = "更新了以下字段: " + ", ".join(updates)
                    logger.info(f"订单 {order_record.order_id} 详细信息已手动更新: {update_message}")
                    return {"status": "success", "message": update_message}
                except Exception as e:
                    logger.error(f"保存订单记录时出错: {str(e)}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    return {"status": "error", "message": f"保存订单记录时出错: {str(e)}"}
            else:
                logger.info(f"订单 {order_record.order_id} 没有需要更新的信息")
                return {"status": "success", "message": "订单信息已是最新，无需更新"}
        else:
            error_msg = order_details.get('error', '未知错误')
            logger.warning(f"获取订单 {order_record.order_id} 详情失败: {error_msg}")
            return {"status": "error", "message": f"获取订单详情失败: {error_msg}"}
    
    except OrderRecord.DoesNotExist:
        error_msg = f"订单记录不存在: id={order_record_id}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"手动更新订单详情时出错: {str(e)}"
        logger.error(error_msg)
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return {"status": "error", "message": error_msg}


def start_order_update_thread(order_record_id):
    """
    启动一个新线程来异步更新订单详情
    
    :param order_record_id: OrderRecord的ID
    """
    logger.info(f"启动订单 {order_record_id} 的更新线程")
    update_thread = threading.Thread(
        target=update_order_details_async,
        args=(order_record_id,),
        name=f"OrderUpdate-{order_record_id}"
    )
    update_thread.daemon = True
    update_thread.start()
    logger.debug(f"已启动订单 {order_record_id} 的更新线程")
    return update_thread