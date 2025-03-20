import logging
import importlib
import os
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status



logger = logging.getLogger(__name__)

# 策略注册表：策略ID -> 策略函数的映射
STRATEGY_REGISTRY = {}

def register_strategy(strategy_id):
    """
    策略注册装饰器
    
    :param strategy_id: 策略ID
    :return: 装饰器函数
    """
    def decorator(strategy_func):
        STRATEGY_REGISTRY[strategy_id] = strategy_func
        logger.info(f"注册策略: ID={strategy_id}, 函数={strategy_func.__name__}")
        return strategy_func
    return decorator

def RunStrategy(strategy_id, alert_data):
    """
    运行指定ID的策略
    
    :param strategy_id: 策略ID
    :param alert_data: 信号数据
    :return: True表示策略验证通过，False表示策略验证失败
    """
    try:
        if strategy_id == 1:
            # 策略ID 1: 默认策略
            from alert.strategy.default_strategy import default_strategy
            logger.info(f"使用默认策略(ID=1)处理信号")
            return default_strategy(strategy_id, alert_data)
        
        # 可以添加其他策略...
            
        else:
            logger.warning(f"未知的策略ID: {strategy_id}")
            return False
            
    except Exception as e:
        logger.error(f"执行策略 {strategy_id} 时出错: {str(e)}")
        return False

# 自动导入所有策略模块
def import_all_strategies():
    """自动导入策略目录下的所有策略模块"""
    strategy_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in os.listdir(strategy_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]  # 移除.py后缀
            module_path = f"alert.strategy.{module_name}"
            try:
                importlib.import_module(module_path)
                logger.info(f"已导入策略模块: {module_path}")
            except ImportError as e:
                logger.error(f"导入策略模块 {module_path} 失败: {str(e)}")

# 在模块加载时自动导入所有策略
import_all_strategies()