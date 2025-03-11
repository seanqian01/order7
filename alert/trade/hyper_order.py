import logging
from alert.models import ContractCode, OrderRecord
from alert.trade.hyperliquid_api import HyperliquidTrader
from alert.core.ordertask import order_monitor
import threading
from django.conf import settings

logger = logging.getLogger(__name__)

def place_hyperliquid_order(alert_data, quantity=None):
    """
    在Hyperliquid交易所下单
    """
    try:
        logger.info(f"开始处理下单请求: symbol={alert_data.symbol}, action={alert_data.action}, contractType={alert_data.contractType}")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 获取当前持仓
        position_result = trader.get_position(alert_data.symbol)
        if position_result["status"] != "success":
            logger.error(f"获取持仓信息失败: {position_result.get('error')}")
            return False
            
        current_position = position_result.get("position")
        logger.info(f"当前持仓信息: {current_position}")
        
        # 判断开平仓
        reduce_only = False
        
        # 先查询交易对配置
        symbol_base = alert_data.symbol.split('-')[0] if '-' in alert_data.symbol else alert_data.symbol
        logger.info(f"查询交易对配置: symbol_base={symbol_base}, 原始symbol={alert_data.symbol}")
        
        # 查询数据库中的默认下单配置
        contract = ContractCode.objects.filter(
            symbol=symbol_base,
            is_active=True
        ).first()
        
        if not contract:
            logger.error(f"未找到交易对 {symbol_base} 的配置,请先在后台设置默认下单数量")
            return False
            
        logger.info(f"找到交易对配置: symbol={contract.symbol}, default_quantity={contract.default_quantity}")
        
        # 情况1: 有持仓时的处理逻辑
        if current_position:
            current_size = current_position.get("size", 0)
            logger.info(f"当前持仓大小: {current_size}")
            
            # 如果当前是多仓(size > 0)且收到sell信号，或者当前是空仓(size < 0)且收到buy信号
            # 使用当前持仓数量来平仓
            if (current_size > 0 and alert_data.action == "sell") or \
               (current_size < 0 and alert_data.action == "buy"):
                reduce_only = True
                quantity = abs(current_size)
                logger.info(f"有持仓且信号方向相反，执行平仓: 方向={alert_data.action}, 使用持仓数量={quantity}")
            else:
                # 同向信号，不进行加仓操作
                logger.warning(f"已有{alert_data.action}方向的持仓，不执行加仓操作")
                return False, "已有同向持仓，为避免风险不执行加仓操作"
        else:
            # 情况2: 无持仓时的处理逻辑
            # 使用数据库中设置的默认下单数量来开仓
            quantity = float(contract.default_quantity)
            logger.info(f"无持仓，执行开仓: 方向={alert_data.action}, 使用默认下单数量={quantity}")
        
        # 下单
        logger.info(f"准备下单: symbol={alert_data.symbol}, action={alert_data.action}, "
                   f"quantity={quantity}, price={alert_data.price}, reduce_only={reduce_only}")
        
        order_response = trader.place_order(
            symbol=alert_data.symbol,
            side=alert_data.action,
            quantity=int(quantity),
            price=float(alert_data.price),
            reduce_only=reduce_only
        )
        
        if order_response["status"] == "success":
            response_data = order_response.get("response", {})
            order_info = order_response.get("order_info", {})
            logger.info(f"下单成功: {order_info}")
            
            # 检查订单状态和订单ID
            if response_data.get("status") == "ok" and order_info.get("order_id"):
                # 创建订单记录
                try:
                    order_record = OrderRecord.objects.create(
                        order_id=str(order_info["order_id"]),  # 确保转换为字符串
                        symbol=alert_data.symbol,
                        side=alert_data.action,
                        price=alert_data.price,
                        quantity=quantity,
                        status="PENDING",
                        filled_quantity=0,
                        reduce_only=reduce_only,
                        is_stop_loss=False  # 这不是止损单
                    )
                    
                    # 启动订单监控线程
                    monitor_thread = threading.Thread(
                        target=order_monitor.monitor_order,
                        args=(order_record.id,)
                    )
                    monitor_thread.daemon = True
                    monitor_thread.start()
                    
                    logger.info(f"订单已创建并开始监控: order_id={order_info['order_id']}")
                    return True
                    
                except Exception as e:
                    logger.error(f"创建订单记录时出错: {str(e)}")
                    return False
            else:
                logger.error(f"下单成功但未获取到订单ID或状态异常: {order_response}")
                return False
        elif order_response["status"] == "error":
            # 移除重复的警告日志，因为具体错误已经在 hyperliquid_api.py 中记录
            return False, order_response["error"]
        else:
            # 下单失败，记录错误信息
            error_msg = order_response.get("error", "Unknown error")
            logger.warning(f"Hyperliquid下单失败: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"处理Hyperliquid交易信号时发生错误: {str(e)}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False

def place_stop_loss_order(original_order_record):
    """
    为已成交的开仓订单创建止损单
    :param original_order_record: 原始订单记录对象
    :return: (bool, str) 成功/失败标志和消息
    """
    try:
        logger.info(f"开始为订单 {original_order_record.order_id} 创建止损单")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 获取交易对配置
        symbol_base = original_order_record.symbol.split('-')[0] if '-' in original_order_record.symbol else original_order_record.symbol
        contract = ContractCode.objects.filter(
            symbol=symbol_base,
            is_active=True
        ).first()
        
        if not contract:
            error_msg = f"未找到交易对 {symbol_base} 的配置，无法下止损单"
            logger.error(error_msg)
            return False, error_msg
        
        # 获取止损百分比和滑点
        stop_loss_percentage = float(contract.stop_loss_percentage)
        stop_loss_slippage = float(contract.stop_loss_slippage)
        
        # 计算止损价格
        # 使用全局配置中的默认杠杆值
        from django.conf import settings
        leverage = float(settings.HYPERLIQUID_CONFIG.get('default_leverage', 1.0))
        logger.info(f"使用全局默认杠杆倍数: {leverage}")

        # 使用实际成交价格而非委托价格
        # 如果有成交均价，使用成交均价；否则使用原始价格
        actual_price = float(original_order_record.avg_price) if original_order_record.avg_price else float(original_order_record.price)
        logger.info(f"使用实际成交价格: {actual_price}")

        if original_order_record.side.lower() == "buy":
            # 多单止损价格 = 开仓价格 - (开仓价格 * 止损百分比 / 100 / 杠杆)
            stop_loss_price = actual_price - (actual_price * stop_loss_percentage / 100 / leverage)
            stop_loss_side = "sell"  # 多单止损方向为卖出
        else:
            # 空单止损价格 = 开仓价格 + (开仓价格 * 止损百分比 / 100 / 杠杆)
            stop_loss_price = actual_price + (actual_price * stop_loss_percentage / 100 / leverage)
            stop_loss_side = "buy"  # 空单止损方向为买入

        # 根据交易对的价格精度进行四舍五入
        # price_precision 表示小数点后的位数
        precision = contract.price_precision
        # 使用交易对的价格精度进行四舍五入
        stop_loss_price = round(stop_loss_price, precision)
        
        # 对于限价止损单，将触发价格和限价设置为相同的值
        # 这样当价格达到触发价格时，会以相同的价格执行订单
        limit_price = stop_loss_price
        
        logger.info(f"准备下止损单: 原订单ID={original_order_record.order_id}, 方向={stop_loss_side}, "
                   f"数量={original_order_record.quantity}, 触发价格={stop_loss_price}, 限价={limit_price}, "
                   f"原价格={actual_price}, 止损百分比={stop_loss_percentage}%")
        
        # 下止损单
        order_response = trader.place_stop_loss_order(
            symbol=original_order_record.symbol,
            side=stop_loss_side,
            quantity=int(float(original_order_record.quantity)),
            trigger_price=stop_loss_price,
            limit_price=limit_price,
            reduce_only=True  # 止损单必须是只减仓
        )
        
        if order_response["status"] == "success":
            order_info = order_response.get("order_info", {})
            logger.info(f"止损单下单成功: {order_info}")
            
            # 创建止损单记录
            try:
                stop_loss_record = OrderRecord.objects.create(
                    order_id=str(order_info["order_id"]),
                    symbol=original_order_record.symbol,
                    side=stop_loss_side,
                    price=stop_loss_price,  # 使用触发价格作为价格
                    quantity=original_order_record.quantity,
                    status="PENDING",
                    filled_quantity=0,
                    reduce_only=True,
                    is_stop_loss=True  # 标记为止损单
                )
                
                # 启动止损单监控线程
                monitor_thread = threading.Thread(
                    target=order_monitor.monitor_order,
                    args=(stop_loss_record.id,)
                )
                monitor_thread.daemon = True
                monitor_thread.start()
                
                success_msg = f"止损单已创建并开始监控: order_id={order_info['order_id']}"
                logger.info(success_msg)
                return True, success_msg
                
            except Exception as e:
                error_msg = f"创建止损单记录时出错: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
        else:
            error_msg = order_response.get("error", "Unknown error")
            logger.error(f"止损单下单失败: {error_msg}")
            return False, f"止损单下单失败: {error_msg}"
    
    except Exception as e:
        error_msg = f"下止损单时出错: {str(e)}"
        logger.error(error_msg)
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False, error_msg