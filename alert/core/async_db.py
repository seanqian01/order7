import threading
from queue import Queue, Empty
import logging
from django.db import transaction, DatabaseError
import time
import threading

logger = logging.getLogger(__name__)

class AsyncDatabaseHandler:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AsyncDatabaseHandler, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.save_queue = Queue()
            self._should_run = True
            self.initialized = True
            
            # 启动数据库处理线程
            self.processing_thread = threading.Thread(target=self._process_saves,
                                                   name="AsyncDBHandler")
            self.processing_thread.daemon = True
            self.processing_thread.start()
            
            logger.info("数据库处理线程已启动")

    def async_save(self, model_instance):
        """异步保存数据库对象"""
        if not self._should_run:
            logger.warning("数据库处理器已停止，无法保存新数据")
            return False

        try:
            self.save_queue.put(model_instance, timeout=5)
            logger.debug(f"数据已加入保存队列: {model_instance.__class__.__name__}")
            return True
        except Exception as e:
            logger.error(f"添加到保存队列时出错: {str(e)}")
            return False

    def _process_saves(self):
        """处理数据库保存队列"""
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self._should_run:
            try:
                # 从队列获取对象，设置1秒超时
                model_instance = self.save_queue.get(timeout=1)
                
                # 记录保存前的对象信息
                model_name = model_instance.__class__.__name__
                model_id = getattr(model_instance, 'id', None)
                model_str = f"{model_name}(id={model_id})"
                
                # 如果是OrderRecord，记录关键字段
                if model_name == 'OrderRecord':
                    key_fields = {
                        'order_id': getattr(model_instance, 'order_id', None),
                        'oid': getattr(model_instance, 'oid', None),
                        'status': getattr(model_instance, 'status', None),
                        'fee': getattr(model_instance, 'fee', None),
                        'filled_time': getattr(model_instance, 'filled_time', None),
                        'filled_quantity': getattr(model_instance, 'filled_quantity', None),
                        'order_type': getattr(model_instance, 'order_type', None)
                    }
                    logger.info(f"准备保存 {model_str}，关键字段: {key_fields}")
                else:
                    logger.debug(f"准备保存 {model_str}")
                
                # 在事务中保存对象
                with transaction.atomic():
                    model_instance.save()
                    
                    # 如果是OrderRecord，再次检查关键字段是否已保存
                    if model_name == 'OrderRecord':
                        saved_instance = model_instance.__class__.objects.get(id=model_id)
                        saved_fields = {
                            'order_id': getattr(saved_instance, 'order_id', None),
                            'oid': getattr(saved_instance, 'oid', None),
                            'status': getattr(saved_instance, 'status', None),
                            'fee': getattr(saved_instance, 'fee', None),
                            'filled_time': getattr(saved_instance, 'filled_time', None),
                            'filled_quantity': getattr(saved_instance, 'filled_quantity', None),
                            'filled_price': getattr(saved_instance, 'filled_price', None),
                            'order_type': getattr(saved_instance, 'order_type', None)
                        }
                        logger.info(f"成功保存 {model_str}，保存后的关键字段: {saved_fields}")
                    else:
                        logger.debug(f"成功保存数据: {model_str}")
                
                # 重置错误计数
                consecutive_errors = 0
                
                # 标记任务完成
                self.save_queue.task_done()
                
            except Empty:
                # 队列为空，正常情况
                consecutive_errors = 0
                continue
            except DatabaseError as e:
                consecutive_errors += 1
                logger.error(f"数据库错误: {str(e)}", exc_info=True)
                
                # 如果连续错误次数过多，暂停一段时间
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(f"检测到连续{consecutive_errors}次数据库错误，暂停60秒")
                    time.sleep(60)
                    consecutive_errors = 0
                else:
                    time.sleep(1)  # 短暂暂停
                    
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"数据库处理线程出错: {str(e)}", exc_info=True)
                time.sleep(0.1)  # 短暂暂停避免频繁错误
                # 标记任务完成，避免队列阻塞
                try:
                    self.save_queue.task_done()
                    logger.warning(f"由于错误，标记任务为完成状态: {str(e)}")
                except Exception as task_error:
                    logger.error(f"标记任务完成时出错: {str(task_error)}")

    def stop(self):
        """停止数据库处理"""
        logger.info("正在停止数据库处理器...")
        self._should_run = False
        
        try:
            # 等待所有任务完成，设置超时时间
            if self.save_queue.all_tasks_done.wait(timeout=30):
                logger.info("所有数据库保存任务已完成")
            else:
                logger.warning("等待数据库保存任务完成超时")
            
            if self.processing_thread.is_alive():
                self.processing_thread.join(timeout=30)
                
            logger.info("数据库处理器已成功停止")
            
        except Exception as e:
            logger.error(f"停止数据库处理器时出错: {str(e)}", exc_info=True)

# 创建全局单例实例
async_db_handler = AsyncDatabaseHandler()