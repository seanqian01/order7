import logging
import time
import datetime
from typing import Optional
from django.conf import settings
from alert.models import OrderRecord
from alert.trade.hyperliquid_api import HyperliquidTrader
import threading
from alert.core.async_db import async_db_handler  # 导入异步数据库处理模块

logger = logging.getLogger(__name__)

class OrderMonitor:
    """订单监控任务"""
    
    def __init__(self):
        self.trader = HyperliquidTrader()
        self._monitor_count = 0
        self._monitor_lock = threading.Lock()
        self._batch_orders_cache = {}
        self._cache_lock = threading.Lock()
        self._last_batch_query_time = 0
        
    def get_config(self) -> dict:
        """获取配置"""
        return {
            'cancel_timeout': settings.ORDER_MANAGEMENT['default']['cancel_timeout'],
            'retry_interval': settings.ORDER_MANAGEMENT['default']['retry_interval'],
            'monitor': settings.ORDER_MONITOR_CONFIG
        }

    def _get_order_status_batch(self, orders_to_check):
        """
        批量获取订单状态
        :param orders_to_check: 要检查的订单列表 [(symbol, order_id), ...]
        :return: {order_id: status_dict, ...}
        """
        current_time = time.time()
        cache_ttl = 2  # 缓存有效期（秒）
        
        # 如果距离上次查询时间不足TTL，直接返回缓存
        if current_time - self._last_batch_query_time < cache_ttl:
            with self._cache_lock:
                return self._batch_orders_cache.copy()
        
        try:
            # 批量查询订单
            with self._cache_lock:
                self._last_batch_query_time = current_time
                self._batch_orders_cache = {}
                
                # 按币种分组订单
                orders_by_coin = {}
                for symbol, order_id in orders_to_check:
                    coin = symbol.split('-')[0] if '-' in symbol else symbol
                    if coin not in orders_by_coin:
                        orders_by_coin[coin] = []
                    orders_by_coin[coin].append(int(order_id))  # 确保order_id是整数
                
                # 批量查询每个币种的订单
                for coin, order_ids in orders_by_coin.items():
                    try:
                        # 使用info.user_state获取用户订单状态
                        user_state = self.trader.info.user_state(self.trader.wallet_address)
                        if user_state and isinstance(user_state, dict):
                            orders = user_state.get('orders', [])
                            for order in orders:
                                order_id = int(order.get('oid', 0))
                                if order_id in order_ids:
                                    # 解析订单状态
                                    status = order.get('status', '')
                                    filled = float(order.get('filled', 0))
                                    total = float(order.get('sz', 0))
                                    
                                    self._batch_orders_cache[order_id] = {
                                        'status': 'success',
                                        'order_status': status,
                                        'filled_quantity': filled,
                                        'total_quantity': total
                                    }
                    except Exception as e:
                        logger.error(f"查询币种 {coin} 的订单状态失败: {str(e)}")
                        continue
                
                return self._batch_orders_cache.copy()
                
        except Exception as e:
            logger.error(f"批量查询订单状态失败: {str(e)}")
            logger.exception(e)
            return {}

    def monitor_order(self, order_record_id: int) -> None:
        """
        监控订单状态
        :param order_record_id: 订单记录ID
        """
        try:
            # 检查并发限制
            with self._monitor_lock:
                if self._monitor_count >= settings.ORDER_MONITOR_CONFIG['max_concurrent']:
                    logger.warning(f"已达到最大并发监控数量 ({settings.ORDER_MONITOR_CONFIG['max_concurrent']})")
                    return
                self._monitor_count += 1
            
            try:
                # 获取订单记录
                order_record = OrderRecord.objects.get(id=order_record_id)
                logger.info(f"开始监控订单: {order_record.order_id}, 委托时间: {order_record.create_time}")
                
                # 获取配置
                config = self.get_config()
                monitor_config = config['monitor']
                cancel_timeout = config['cancel_timeout']
                
                # 添加详细日志，输出实际使用的配置值
                logger.info(f"订单 {order_record.order_id} 监控配置: cancel_timeout={cancel_timeout}秒, "
                           f"initial_interval={monitor_config['initial_interval']}秒, "
                           f"normal_interval={monitor_config['normal_interval']}秒, "
                           f"intensive_interval={monitor_config['intensive_interval']}秒")
                
                start_time = datetime.datetime.now()
                logger.debug(f"订单监控开始时间: {start_time}, 超时时间: {cancel_timeout}秒")
                
                cancel_retry_count = 0
                max_cancel_retries = 2
                current_interval = monitor_config['initial_interval']
                
                # 初始状态检查 - 使用新的直接查询方法
                initial_status = self.trader.get_order_status(order_record.symbol, order_record.order_id)
                if initial_status and initial_status["status"] == "success":
                    if initial_status["order_status"] == "FILLED":
                        # 订单已成交，直接处理成交逻辑
                        order_record.status = "FILLED"
                        order_record.filled_quantity = initial_status["filled_quantity"]
                        async_db_handler.async_save(order_record)  # 使用异步保存
                        logger.info(f"订单 {order_record.order_id} 已成交: {initial_status['filled_quantity']}张")
                        
                        # 异步更新订单详情（oid、fee、filled_time等）
                        from alert.core.async_order_record import update_order_details_async
                        logger.info(f"订单 {order_record.order_id} 已成交，异步更新订单详情")
                        update_order_details_async(order_record.id)
                        
                        # 处理成交后的逻辑
                        should_end_monitor = self._handle_filled_order(order_record)
                        if should_end_monitor:
                            logger.info(f"订单 {order_record.order_id} 处理完成，结束监控线程")
                            return
                        else:
                            logger.info(f"订单 {order_record.order_id} 成交后继续监控")
                        
                    elif initial_status["order_status"] in ["PENDING", "PARTIALLY_FILLED"]:
                        order_record.status = "SUBMITTED"
                        if initial_status["order_status"] == "PARTIALLY_FILLED":
                            order_record.filled_quantity = initial_status["filled_quantity"]
                        async_db_handler.async_save(order_record)  # 使用异步保存
                        logger.info(f"订单 {order_record.order_id} 已确认提交，状态: {initial_status['order_status']}")
                
                # 记录上次状态，用于检测状态变化
                last_status = initial_status["order_status"] if initial_status and initial_status["status"] == "success" else "UNKNOWN"
                last_filled = initial_status["filled_quantity"] if initial_status and initial_status["status"] == "success" else 0
                status_check_count = 0
                
                # 初始化部分成交检测变量
                detected_partial_fill = False
                partial_fill_time = None
                
                # 本地计时监控
                while True:
                    current_time = datetime.datetime.now()
                    elapsed_time = (current_time - start_time).total_seconds()
                    remaining_time = cancel_timeout - elapsed_time
                    status_check_count += 1
                    
                    # 动态调整检查间隔
                    if remaining_time <= monitor_config['intensive_threshold']:
                        current_interval = monitor_config['intensive_interval']
                        if status_check_count % 5 == 0:  # 每5次检查才记录一次日志
                            logger.debug(f"订单 {order_record.order_id} 接近超时，切换到密集检查模式")
                    else:
                        current_interval = monitor_config['normal_interval']
                    
                    # 使用新的直接查询方法获取订单状态
                    order_status = self.trader.get_order_status(order_record.symbol, order_record.order_id)
                    
                    if order_status and order_status["status"] == "success":
                        current_status = order_status["order_status"]
                        current_filled = order_status.get("filled_quantity", 0)
                        
                        # 只有在状态变化时才记录详细日志
                        status_changed = current_status != last_status
                        filled_changed = current_filled != last_filled
                        
                        if status_changed or filled_changed:
                            if current_status == "FILLED":
                                order_record.status = "FILLED"
                                order_record.filled_quantity = current_filled
                                async_db_handler.async_save(order_record)  # 使用异步保存
                                logger.info(f"订单 {order_record.order_id} 已成交: {current_filled}张")
                                
                                # 异步更新订单详情（oid、fee、filled_time等）
                                from alert.core.async_order_record import update_order_details_async
                                logger.info(f"订单 {order_record.order_id} 已成交，异步更新订单详情")
                                update_order_details_async(order_record.id)
                                
                                # 处理成交后的逻辑
                                should_end_monitor = self._handle_filled_order(order_record)
                                if should_end_monitor:
                                    logger.info(f"订单 {order_record.order_id} 处理完成，结束监控线程")
                                    break
                                else:
                                    logger.info(f"订单 {order_record.order_id} 成交后继续监控")
                                
                            elif current_status == "PARTIALLY_FILLED":
                                order_record.status = "PARTIALLY_FILLED"
                                order_record.filled_quantity = current_filled
                                async_db_handler.async_save(order_record)  # 使用异步保存
                                logger.info(f"订单 {order_record.order_id} 部分成交: {current_filled}张")
                                
                                # 异步更新订单详情（oid、fee、filled_time等）
                                from alert.core.async_order_record import update_order_details_async
                                logger.info(f"订单 {order_record.order_id} 部分成交，异步更新订单详情")
                                update_order_details_async(order_record.id)
                            elif status_changed:
                                logger.info(f"订单 {order_record.order_id} 状态变化: {last_status} -> {current_status}")
                        
                        # 更新上次状态
                        last_status = current_status
                        last_filled = current_filled
                    
                    # 检查是否需要撤单
                    if elapsed_time > cancel_timeout and not order_record.is_stop_loss:
                        logger.info(f"订单 {order_record.order_id} 已超时 {elapsed_time:.1f}秒，准备撤单")
                        
                        # 撤单前再次检查状态
                        final_check = self.trader.get_order_status(order_record.symbol, order_record.order_id)
                        if final_check and final_check["status"] == "success":
                            # 如果订单已完全成交
                            if final_check["order_status"] == "FILLED":
                                order_record.status = "FILLED"
                                order_record.filled_quantity = final_check["filled_quantity"]
                                async_db_handler.async_save(order_record)  # 使用异步保存
                                logger.info(f"订单 {order_record.order_id} 在撤单前发现已成交")
                                
                                # 异步更新订单详情（oid、fee、filled_time等）
                                from alert.core.async_order_record import update_order_details_async
                                logger.info(f"订单 {order_record.order_id} 已成交，异步更新订单详情")
                                update_order_details_async(order_record.id)
                                
                                # 处理成交后的逻辑
                                should_end_monitor = self._handle_filled_order(order_record)
                                if should_end_monitor:
                                    logger.info(f"订单 {order_record.order_id} 处理完成，结束监控线程")
                                    break
                                else:
                                    logger.info(f"订单 {order_record.order_id} 成交后继续监控")
                            
                            # 如果订单部分成交
                            elif final_check["order_status"] == "PARTIALLY_FILLED":
                                # 标记检测到部分成交
                                detected_partial_fill = True
                                
                                # 更新订单记录
                                order_record.status = "PARTIALLY_FILLED"
                                order_record.filled_quantity = final_check["filled_quantity"]
                                async_db_handler.async_save(order_record)  # 使用异步保存
                                
                                logger.info(f"订单 {order_record.order_id} 在超时时仍然是部分成交状态，处理未成交部分")
                                
                                # 异步更新订单详情（oid、fee、filled_time等）
                                from alert.core.async_order_record import update_order_details_async
                                logger.info(f"订单 {order_record.order_id} 部分成交，异步更新订单详情")
                                update_order_details_async(order_record.id)
                                
                                # 为已成交部分启动止损单
                                if order_record.filled_quantity > 0:
                                    logger.info(f"为部分成交订单 {order_record.order_id} 的已成交部分 ({order_record.filled_quantity}张) 启动止损")
                                    
                                    # 记录原始数量
                                    original_quantity = order_record.quantity
                                    
                                    # 临时修改订单数量为已成交数量
                                    order_record.quantity = order_record.filled_quantity
                                    
                                    # 导入止损单下单函数
                                    from alert.trade.hyper_order import place_stop_loss_order
                                    
                                    # 下止损单
                                    success, message = place_stop_loss_order(order_record)
                                    
                                    # 恢复原始数量
                                    order_record.quantity = original_quantity
                                    
                                    if success:
                                        logger.info(f"部分成交订单的止损单已完成: {message}")
                                    else:
                                        logger.error(f"部分成交订单的止损单报错: {message}")
                        
                        # 执行撤单
                        while cancel_retry_count < max_cancel_retries:
                            cancel_result = self.trader.cancel_order_by_id(order_record.symbol, order_record.order_id)
                            if cancel_result["status"] == "success":
                                # 更新订单状态
                                if detected_partial_fill:
                                    # 如果是部分成交，保持状态为PARTIALLY_FILLED
                                    logger.info(f"部分成交订单 {order_record.order_id} 的未成交部分已撤单成功")
                                else:
                                    # 如果完全未成交，则标记为已取消
                                    order_record.status = "CANCELLED"
                                    async_db_handler.async_save(order_record)  # 使用异步保存
                                    logger.info(f"订单 {order_record.order_id} 撤单成功")
                                    
                                    # 已取消的订单不需要再查询详情
                                    # 注释掉以下代码，避免不必要的API查询
                                    # from alert.core.async_order_record import update_order_details_async
                                    # logger.info(f"订单 {order_record.order_id} 已取消，异步更新订单详情")
                                    # update_order_details_async(order_record.id)
                                return
                            
                            cancel_retry_count += 1
                            error_msg = cancel_result.get('error', 'Unknown error')
                            logger.error(f"订单 {order_record.order_id} 撤单失败 (第{cancel_retry_count}次): {error_msg}")
                            
                            # 如果撤单失败，等待一段时间后重试
                            time.sleep(config['retry_interval'])
                        
                        # 如果所有撤单尝试都失败
                        logger.error(f"订单 {order_record.order_id} 撤单失败，已达到最大重试次数")
                        break
                    
                    # 等待下一次检查
                    time.sleep(current_interval)
                    
                    # 每10次检查输出一次调试信息
                    if status_check_count % 10 == 0:
                        logger.debug(f"订单 {order_record.order_id} 监控中: 已经过{elapsed_time:.1f}秒，状态={last_status}")
                
            except OrderRecord.DoesNotExist:
                logger.error(f"订单记录不存在: ID={order_record_id}")
            except Exception as e:
                logger.error(f"监控订单时出错: {str(e)}")
                logger.exception(e)
            finally:
                # 减少并发计数
                with self._monitor_lock:
                    self._monitor_count -= 1
                    
        except Exception as e:
            logger.error(f"订单监控线程异常: {str(e)}")
            logger.exception(e)

    def _handle_filled_order(self, order_record):
        """
        处理已成交订单的后续操作
        :param order_record: 订单记录对象
        :return: 如果返回 True，表示应该结束监控线程
        """
        try:
            logger.info(f"处理已成交订单: {order_record.order_id}")
            
            # 判断是开仓还是平仓订单
            if order_record.reduce_only:
                # 平仓订单成交
                if order_record.is_stop_loss:
                    logger.info(f"止损单 {order_record.order_id} 已成交，完成下单策略")
                else:
                    logger.info(f"平仓订单 {order_record.order_id} 已成交，完成下单策略")
                # 不需要再轮询订单状态，也不需要走撤单策略
                return True
            else:
                # 开仓订单成交，需要下止损单
                logger.info(f"开仓订单 {order_record.order_id} 已成交，准备下止损单")
                
                # 导入止损单下单函数
                from alert.trade.hyper_order import place_stop_loss_order
                
                # 下止损单
                success, message = place_stop_loss_order(order_record)
                if success:
                    logger.info(f"止损单已完成: {message}")
                    # 止损单已成功委托，结束原订单的监控线程
                    return True
                else:
                    logger.error(f"止损单报错: {message}")
                    # 即使止损单下单失败，也应该结束当前订单的监控，因为主订单已经成交
                    return True
        
        except Exception as e:
            logger.error(f"处理已成交订单时出错: {str(e)}")
            logger.exception(e)
            # 发生异常时也应该结束监控线程，因为继续监控可能会导致重复处理
            return True

    def check_pending_orders(self) -> None:
        """
        检查所有未完成的订单
        用于系统重启后恢复订单监控
        """
        try:
            # 获取所有未完成的订单
            pending_orders = OrderRecord.objects.filter(
                status__in=["PENDING", "SUBMITTED", "PARTIALLY_FILLED"]
            )
            
            # 获取配置
            config = self.get_config()
            
            for order in pending_orders:
                # 如果订单已经超时，直接标记为失败
                if order.create_time:
                    elapsed_time = (datetime.datetime.now() - order.create_time).total_seconds()
                    if elapsed_time > config["cancel_timeout"] * (config["max_retries"] + 1):
                        order.status = "FAILED"
                        async_db_handler.async_save(order)  # 使用异步保存
                        logger.warning(f"订单 {order.order_id} 已超时，标记为失败")
                        continue
                
                # 重新开始监控订单
                self.monitor_order(order.id)
                
        except Exception as e:
            logger.error(f"检查未完成订单时出错: {str(e)}")

# 创建全局订单监控器实例
order_monitor = OrderMonitor()