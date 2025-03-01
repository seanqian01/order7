import logging
import os
from logging.handlers import RotatingFileHandler
from collections import deque
from datetime import datetime

class ReverseLogHandler(RotatingFileHandler):
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self.buffer = deque(maxlen=1000)  # 保存最近1000条日志
        
    def emit(self, record):
        """
        重写emit方法，实现倒序写入日志
        """
        try:
            # 将新日志添加到缓冲区开头
            msg = self.format(record)
            self.buffer.appendleft(msg)
            
            # 将整个缓冲区写入文件
            with open(self.baseFilename, 'w', encoding=self.encoding) as f:
                for line in self.buffer:
                    f.write(line + '\n')
                    
        except Exception as e:
            self.handleError(record)

def setup_logger(name='alert', log_file='order7.log', level=logging.DEBUG):
    """
    设置一个支持倒序记录的logger
    
    :param name: logger名称
    :param log_file: 日志文件名
    :param level: 日志级别
    :return: logger实例
    """
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    # 创建formatter
    formatter = logging.Formatter(
        '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
        style='{'
    )
    
    # 创建自定义的handler
    handler = ReverseLogHandler(log_file)
    handler.setFormatter(formatter)
    
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 移除现有的handlers
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    
    # 添加新的handler
    logger.addHandler(handler)
    
    return logger

# 创建默认logger实例
default_logger = setup_logger(
    log_file=os.path.join(os.path.dirname(__file__), 'order7.log')
)