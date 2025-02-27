import logging
import time
import datetime
from typing import Optional
from django.conf import settings
from alert.models import OrderRecord
from alert.trade.hyperliquid_api import HyperliquidTrader
import threading

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
                logger.info(f"开始监控订单: {order_record.order_id}, 委托时间: {order_record.created_at}")
                
                # 获取配置
                config = self.get_config()
                monitor_config = config['monitor']
                cancel_timeout = config['cancel_timeout']
                
                start_time = datetime.datetime.now()
                logger.info(f"订单监控开始时间: {start_time}, 超时时间: {cancel_timeout}秒")
                
                cancel_retry_count = 0
                max_cancel_retries = 2
                current_interval = monitor_config['initial_interval']
                
                # 初始状态检查
                initial_status = self._get_order_status_batch([(order_record.symbol, order_record.order_id)]).get(order_record.order_id)
                if initial_status and initial_status["status"] == "success":
                    order_record.status = "SUBMITTED"
                    order_record.save()
                    logger.info(f"订单 {order_record.order_id} 已确认提交")
                
                # 本地计时监控
                while True:
                    current_time = datetime.datetime.now()
                    elapsed_time = (current_time - start_time).total_seconds()
                    remaining_time = cancel_timeout - elapsed_time
                    
                    # 动态调整检查间隔
                    if remaining_time <= monitor_config['intensive_threshold']:
                        current_interval = monitor_config['intensive_interval']
                        logger.info(f"订单 {order_record.order_id} 接近超时，切换到密集检查模式")
                    else:
                        current_interval = monitor_config['normal_interval']
                    
                    # 获取订单状态（批量查询）
                    order_status = self._get_order_status_batch([(order_record.symbol, order_record.order_id)]).get(order_record.order_id)
                    
                    if order_status and order_status["status"] == "success":
                        filled_quantity = order_status.get("filled_quantity", 0)
                        if filled_quantity > 0:
                            order_record.status = "FILLED"
                            order_record.filled_quantity = filled_quantity
                            order_record.save()
                            logger.info(f"订单 {order_record.order_id} 已成交: {filled_quantity}张")
                            break
                    
                    # 检查是否需要撤单
                    if elapsed_time > cancel_timeout:
                        logger.info(f"订单 {order_record.order_id} 已超时 {elapsed_time}秒，准备撤单")
                        
                        # 撤单前再次检查状态
                        final_check = self._get_order_status_batch([(order_record.symbol, order_record.order_id)]).get(order_record.order_id)
                        if final_check and final_check.get("filled_quantity", 0) > 0:
                            order_record.status = "FILLED"
                            order_record.filled_quantity = final_check["filled_quantity"]
                            order_record.save()
                            logger.info(f"订单 {order_record.order_id} 在撤单前发现已成交")
                            break
                        
                        # 执行撤单
                        while cancel_retry_count < max_cancel_retries:
                            cancel_result = self.trader.cancel_order_by_id(order_record.symbol, order_record.order_id)
                            if cancel_result["status"] == "success":
                                order_record.status = "CANCELLED"
                                order_record.save()
                                logger.info(f"订单 {order_record.order_id} 撤单成功")
                                return
                            
                            cancel_retry_count += 1
                            error_msg = cancel_result.get('error', 'Unknown error')
                            logger.error(f"订单 {order_record.order_id} 撤单失败 (第{cancel_retry_count}次): {error_msg}")
                            
                            if cancel_retry_count >= max_cancel_retries:
                                order_record.status = "FAILED"
                                order_record.save()
                                logger.error(f"订单 {order_record.order_id} 已达到最大撤单重试次数 ({max_cancel_retries})")
                                return
                            
                            time.sleep(current_interval)
                    
                    time.sleep(current_interval)
                    
            finally:
                # 释放并发计数
                with self._monitor_lock:
                    self._monitor_count -= 1
                
        except OrderRecord.DoesNotExist:
            logger.error(f"订单记录不存在: {order_record_id}")
        except Exception as e:
            logger.error(f"监控订单状态时出错: {str(e)}")
            logger.exception(e)

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
                if order.created_at:
                    elapsed_time = (datetime.datetime.now() - order.created_at).total_seconds()
                    if elapsed_time > config["cancel_timeout"] * (config["max_retries"] + 1):
                        order.status = "FAILED"
                        order.save()
                        logger.warning(f"订单 {order.order_id} 已超时，标记为失败")
                        continue
                
                # 重新开始监控订单
                self.monitor_order(order.id)
                
        except Exception as e:
            logger.error(f"检查未完成订单时出错: {str(e)}")

# 创建全局订单监控器实例
order_monitor = OrderMonitor()