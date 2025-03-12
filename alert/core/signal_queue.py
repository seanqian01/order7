import threading
from queue import PriorityQueue, Empty
from datetime import datetime
import logging
from django.db import transaction
from alert.view.filter_signal import filter_trade_signal
from alert.trade.hyper_order import place_hyperliquid_order
from rest_framework import status
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
import time

logger = logging.getLogger(__name__)

class SignalQueueProcessor:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SignalQueueProcessor, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            # 从settings获取配置，如果没有则使用默认值
            self.max_workers = getattr(settings, 'SIGNAL_QUEUE_MAX_WORKERS', 5)
            self.queue_size = getattr(settings, 'SIGNAL_QUEUE_MAX_SIZE', 1000)
            
            # 使用限制大小的优先级队列
            self.signal_queue = PriorityQueue(maxsize=self.queue_size)
            self._should_run = True
            self.initialized = True
            
            # 创建线程池
            self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers,
                                                thread_name_prefix="SignalProcessor")
            
            # 启动队列监控线程
            self.queue_monitor_thread = threading.Thread(target=self._monitor_queue,
                                                       name="SignalQueueMonitor")
            self.queue_monitor_thread.daemon = True
            self.queue_monitor_thread.start()
            
            logger.info(f"信号处理器已初始化 (最大线程数: {self.max_workers}, 队列大小: {self.queue_size})")

    def add_signal(self, signal_data):
        """将信号添加到处理队列"""
        if not self._should_run:
            logger.warning("信号处理器已停止，无法添加新信号")
            return False

        try:
            priority = datetime.now().timestamp()
            
            if self.signal_queue.full():
                logger.warning("信号队列已满，等待处理空间...")
            
            self.signal_queue.put((priority, signal_data), timeout=5)
            logger.info(f"信号已加入队列: {signal_data.symbol} {signal_data.action}")
            return True
            
        except Exception as e:
            logger.error(f"添加信号到队列时出错: {str(e)}")
            return False

    def _process_single_signal(self, signal_data):
        """处理单个信号"""
        try:
            logger.info(f"开始处理信号: {signal_data.symbol} {signal_data.action}")
            
            # 调用过滤函数
            response = filter_trade_signal(signal_data)

            # 根据过滤结果处理信号
            if response.status_code == status.HTTP_200_OK:
                if signal_data.contractType == 3:  # 虚拟货币
                    success = place_hyperliquid_order(signal_data)
                    if success:
                        logger.info(f"信号处理成功: {signal_data.symbol}")
                    else:
                        logger.error(f"信号处理失败: {signal_data.symbol}")
                else:
                    logger.info(f"非Hyperliquid渠道信号: {signal_data.symbol}")
            else:
                logger.warning(f"信号未通过过滤: {signal_data.symbol}, 原因: {response.data.get('message', '未知原因')}")

        except Exception as e:
            logger.error(f"处理信号时出错: {str(e)}", exc_info=True)

    def _monitor_queue(self):
        """监控队列并分发任务到线程池"""
        while self._should_run:
            try:
                # 从队列获取信号，设置1秒超时
                priority, signal_data = self.signal_queue.get(timeout=1)
                
                # 提交到线程池处理
                self.thread_pool.submit(self._process_single_signal, signal_data)
                
                # 标记任务完成
                self.signal_queue.task_done()
                
            except Empty:
                # 队列为空，正常情况，继续等待
                continue
            except Exception as e:
                logger.error(f"信号处理线程出错: {str(e)}", exc_info=True)
                # 添加短暂延迟避免过于频繁的错误日志
                time.sleep(0.1)

    def stop(self):
        """停止信号处理"""
        logger.info("正在停止信号处理器...")
        self._should_run = False
        
        try:
            # 等待所有任务完成，设置超时时间
            if self.signal_queue.all_tasks_done.wait(timeout=30):
                logger.info("所有信号处理任务已完成")
            else:
                logger.warning("等待信号处理任务完成超时")
            
            # 关闭线程池
            self.thread_pool.shutdown(wait=True, timeout=30)
            
            if self.queue_monitor_thread.is_alive():
                self.queue_monitor_thread.join(timeout=30)
            
            logger.info("信号处理器已成功停止")
            
        except Exception as e:
            logger.error(f"停止信号处理器时出错: {str(e)}", exc_info=True)

# 创建全局单例实例
signal_processor = SignalQueueProcessor()