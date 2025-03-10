import sys
import logging
import functools
from functools import wraps

logger = logging.getLogger(__name__)

def is_migration_command():
    """
    检查当前执行的命令是否为数据库迁移相关命令
    
    Returns:
        bool: 如果当前命令是 makemigrations 或 migrate，返回 True，否则返回 False
    """
    for arg in sys.argv:
        if 'makemigrations' in arg or 'migrate' in arg:
            return True
    return False

def is_runserver_command():
    """
    检查当前执行的命令是否为 runserver 命令
    
    Returns:
        bool: 如果当前命令是 runserver，返回 True，否则返回 False
    """
    for arg in sys.argv:
        if 'runserver' in arg:
            return True
    return False

def skip_during_migrations(func):
    """
    装饰器：在数据库迁移命令执行期间跳过被装饰的函数
    
    Args:
        func: 要装饰的函数
        
    Returns:
        wrapper: 装饰后的函数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if is_migration_command():
            logger.debug(f"数据库迁移期间跳过函数: {func.__name__}")
            return None
        return func(*args, **kwargs)
    return wrapper

def initialize_channels(force=False):
    """
    初始化所有渠道连接
    
    此函数应该在应用启动时调用，用于初始化所有渠道连接。
    在数据库迁移期间会自动跳过初始化，除非 force 参数设置为 True。
    
    Args:
        force (bool): 如果为 True，则即使在迁移期间也会强制初始化渠道
        
    Returns:
        bool: 初始化是否成功完成
    """
    if is_migration_command() and not force:
        logger.debug("检测到数据库迁移命令，跳过渠道初始化")
        return False
    
    try:
        # 这里添加渠道初始化的代码
        # 例如：初始化 HyperliquidTrader 等
        logger.debug("渠道初始化成功完成")
        return True
    except Exception as e:
        logger.error(f"渠道初始化失败: {str(e)}")
        return False

def skip_channel_init(func):
    """
    装饰器：在数据库迁移命令执行期间跳过渠道初始化
    
    Args:
        func: 要装饰的函数
        
    Returns:
        wrapper: 装饰后的函数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if is_migration_command():
            logger.debug("数据库迁移期间跳过渠道初始化")
            return None
        return func(*args, **kwargs)
    return wrapper

def patch_hyperliquid_trader():
    """
    修补 HyperliquidTrader 类，确保在迁移命令执行期间不会进行渠道初始化
    
    此函数应该在应用启动时尽早调用，以确保在任何 HyperliquidTrader 实例化之前
    修改其初始化方法。
    """
    if not is_migration_command():
        logger.debug("非迁移命令，不需要修补 HyperliquidTrader")
        return
    
    try:
        # 导入 HyperliquidTrader 类
        from alert.trade.hyperliquid_api import HyperliquidTrader
        
        # 保存原始的 __init__ 方法
        original_init = HyperliquidTrader.__init__
        
        # 定义新的 __init__ 方法
        @wraps(original_init)
        def new_init(self, wallet_address=None, api_secret=None):
            logger.debug("迁移命令期间跳过 HyperliquidTrader 初始化")
            # 设置基本属性，但不进行实际的初始化
            self.account = None
            self.info = None
            self.exchange = None
            self.exchange_instance = None
            self._ws = None
            self._ws_connected = False
            self._ws_lock = None
            self._ws_thread = None
            self._ws_should_run = False
        
        # 替换 __init__ 方法
        HyperliquidTrader.__init__ = new_init
        logger.debug("成功修补 HyperliquidTrader.__init__ 方法")
    except ImportError:
        logger.warning("无法导入 HyperliquidTrader 类，跳过修补")
    except Exception as e:
        logger.error(f"修补 HyperliquidTrader 时出错: {str(e)}")

# 应用启动时的初始化函数
@skip_channel_init
def initialize_application():
    """
    应用程序启动时的初始化函数
    
    此函数应该在应用的 AppConfig.ready() 方法中调用，
    用于执行所有必要的初始化操作。
    """
    # 首先修补 HyperliquidTrader 类
    patch_hyperliquid_trader()
    
    # 只在 runserver 命令时初始化渠道
    if is_runserver_command():
        initialize_channels()
    elif is_migration_command():
        logger.debug("数据库迁移期间跳过应用初始化")
    else:
        # 其他命令可能需要部分初始化
        logger.debug("执行其他命令的部分初始化")