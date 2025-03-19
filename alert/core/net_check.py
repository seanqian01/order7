import logging
import threading
import time
import ssl
import json
import websocket
from typing import Optional, Callable, Dict, Any, List

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    WebSocket连接管理器
    负责WebSocket连接的生命周期管理，包括：
    1. 按需建立连接
    2. 闲置自动断开
    3. 连接错误重试
    4. 消息处理
    """
    
    def __init__(self, 
                 url: str, 
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
                 idle_timeout: int = 60,
                 max_retries: int = 3,
                 ping_interval: int = 30,
                 ping_timeout: int = 10):
        """
        初始化WebSocket管理器
        
        Args:
            url: WebSocket服务器URL
            on_message: 消息处理回调函数
            idle_timeout: 闲置超时时间（秒），超过此时间无活动将自动断开连接
            max_retries: 连接失败时的最大重试次数
            ping_interval: ping间隔时间（秒）
            ping_timeout: ping超时时间（秒）
        """
        self.url = url
        self.on_message_callback = on_message
        self.idle_timeout = idle_timeout
        self.max_retries = max_retries
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        
        # WebSocket连接状态
        self._ws = None
        self._ws_connected = False
        self._ws_lock = threading.Lock()
        self._ws_thread = None
        self._ws_should_run = False
        
        # 闲置管理
        self._idle_timer = None
        self._last_activity_time = 0
        
        logger.info(f"WebSocketManager初始化完成，URL: {url}, 闲置超时: {idle_timeout}秒")
    
    def _on_ws_open(self, ws):
        """WebSocket连接建立时的回调"""
        with self._ws_lock:
            self._ws_connected = True
            self._last_activity_time = time.time()
        
        logger.info(f"WebSocket连接已建立: {self.url}")
        
        # 不再需要重新订阅功能
        
        # 启动闲置计时器
        self._start_idle_timer()
    
    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭时的回调"""
        with self._ws_lock:
            self._ws_connected = False
            self._cancel_idle_timer()
        
        close_info = f"状态码: {close_status_code}" if close_status_code else "无状态码"
        close_info += f", 消息: {close_msg}" if close_msg else ", 无消息"
        logger.info(f"WebSocket连接已关闭 ({close_info})")
    
    def _on_ws_error(self, ws, error):
        """WebSocket错误时的回调"""
        if isinstance(error, ConnectionResetError):
            logger.warning(f"WebSocket连接被重置: {error}")
        else:
            logger.warning(f"WebSocket错误: {error}")
    
    def _on_ws_message(self, ws, message):
        """WebSocket消息处理"""
        try:
            # 更新最后活动时间
            self._last_activity_time = time.time()
            # 重置闲置计时器
            self._reset_idle_timer()
            
            # 解析消息
            data = json.loads(message)
            logger.debug(f"收到WebSocket消息: {data}")
            
            # 调用用户定义的回调函数
            if self.on_message_callback:
                self.on_message_callback(data)
                
        except Exception as e:
            logger.warning(f"处理WebSocket消息时出错: {str(e)}")
    
    def _ws_connect(self):
        """
        建立WebSocket连接，包含重试机制
        """
        retry_count = 0
        retry_delay = 2  # 初始重试延迟（秒）
        
        while retry_count < self.max_retries and self._ws_should_run:
            try:
                logger.debug(f"正在连接WebSocket (尝试 {retry_count+1}/{self.max_retries}): {self.url}")
                
                # 创建WebSocket连接
                self._ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close
                )
                
                # 更健壮的WebSocket设置
                self._ws.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    skip_utf8_validation=True,
                    reconnect=5  # 启用内部重连机制
                )
                
                # 如果run_forever返回，说明连接已关闭
                logger.debug("WebSocket run_forever已退出")
                break
                
            except ConnectionResetError as e:
                retry_count += 1
                logger.warning(f"WebSocket连接被重置 (尝试 {retry_count}/{self.max_retries}): {str(e)}")
                if retry_count < self.max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避策略
                
            except Exception as e:
                retry_count += 1
                logger.error(f"WebSocket连接出错 (尝试 {retry_count}/{self.max_retries}): {str(e)}")
                if retry_count < self.max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避策略
        
        # 如果所有重试都失败
        if retry_count >= self.max_retries:
            logger.error("WebSocket连接在多次尝试后仍然失败")
            with self._ws_lock:
                self._ws_connected = False
    
    def _start_idle_timer(self):
        """启动闲置计时器"""
        with self._ws_lock:
            # 取消现有计时器
            self._cancel_idle_timer()
            
            # 创建新计时器
            if self.idle_timeout > 0:
                self._idle_timer = threading.Timer(self.idle_timeout, self._on_idle_timeout)
                self._idle_timer.daemon = True
                self._idle_timer.start()
                logger.debug(f"启动闲置计时器，{self.idle_timeout}秒后将断开连接")
    
    def _reset_idle_timer(self):
        """重置闲置计时器"""
        if self._idle_timer:
            self._start_idle_timer()  # 重新启动计时器
    
    def _cancel_idle_timer(self):
        """取消闲置计时器"""
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None
    
    def _on_idle_timeout(self):
        """闲置超时处理"""
        with self._ws_lock:
            current_time = time.time()
            idle_time = current_time - self._last_activity_time
            
            if idle_time >= self.idle_timeout and self._ws_connected:
                logger.info(f"WebSocket连接闲置超过{self.idle_timeout}秒，自动断开连接")
                self.disconnect()
    
    # 移除订阅相关功能
    
    def ensure_connected(self):
        """
        确保WebSocket连接已建立，仅在需要时建立连接
        
        Returns:
            bool: 连接是否成功
        """
        with self._ws_lock:
            # 更新最后活动时间
            self._last_activity_time = time.time()
            
            # 如果已经连接，重置闲置计时器并返回
            if self._ws_connected:
                self._reset_idle_timer()
                return True
            
            # 如果已经有一个线程在尝试连接，但连接尚未建立
            if not self._ws_connected and self._ws_thread and self._ws_thread.is_alive():
                logger.debug("WebSocket连接正在进行中，等待连接完成")
                # 等待连接建立或超时
                timeout = 8  # 增加超时时间到8秒
                start_time = time.time()
                while not self._ws_connected and time.time() - start_time < timeout:
                    time.sleep(0.2)  # 稍微增加等待间隔，减少CPU使用
                
                if not self._ws_connected:
                    logger.warning("等待现有WebSocket连接超时，将继续执行")
                    return False
                return True
            
            # 如果没有活跃的连接线程，则创建一个新的
            if not self._ws_connected and (not self._ws_thread or not self._ws_thread.is_alive()):
                logger.debug("正在按需建立新的WebSocket连接")
                
                # 清理旧线程（如果有）
                if self._ws_thread:
                    self._ws_thread = None
                
                # 取消任何存在的闲置计时器
                self._cancel_idle_timer()
                
                self._ws_should_run = True
                self._ws_thread = threading.Thread(target=self._ws_connect)
                self._ws_thread.daemon = True
                self._ws_thread.start()
                
                # 等待连接建立或超时
                timeout = 8  # 增加超时时间到8秒
                start_time = time.time()
                while not self._ws_connected and time.time() - start_time < timeout:
                    time.sleep(0.2)  # 稍微增加等待间隔，减少CPU使用
                
                if not self._ws_connected:
                    logger.warning("新的WebSocket连接未能在预期时间内建立，将继续执行")
                    return False
                return True
        
        return self._ws_connected
    
    def disconnect(self):
        """
        主动断开WebSocket连接
        """
        with self._ws_lock:
            self._cancel_idle_timer()
            self._ws_should_run = False
            
            if self._ws:
                try:
                    self._ws.close()
                    logger.info("主动断开WebSocket连接")
                except Exception as e:
                    logger.error(f"断开WebSocket连接时出错: {str(e)}")
            
            self._ws_connected = False
    
    def send(self, data):
        """
        发送WebSocket消息
        
        Args:
            data: 要发送的消息，可以是字典或字符串
        
        Returns:
            bool: 发送是否成功
        """
        # 确保连接已建立
        if not self.ensure_connected():
            logger.error("发送消息失败：WebSocket未连接")
            return False
        
        try:
            # 如果是字典，转换为JSON字符串
            if isinstance(data, dict):
                message = json.dumps(data)
            else:
                message = str(data)
            
            # 发送消息
            self._ws.send(message)
            
            # 更新最后活动时间
            self._last_activity_time = time.time()
            # 重置闲置计时器
            self._reset_idle_timer()
            
            logger.debug(f"WebSocket消息已发送: {message[:100]}...")
            return True
            
        except Exception as e:
            logger.error(f"发送WebSocket消息时出错: {str(e)}")
            return False
    
    def subscribe(self, subscription_data):
        """
        发送订阅消息（简化版，不再保存订阅列表）
        
        Args:
            subscription_data: 订阅数据
        
        Returns:
            bool: 发送是否成功
        """
        # 直接发送消息，不保存订阅列表
        return self.send(subscription_data)
    
    def unsubscribe(self, subscription_data):
        """
        发送取消订阅消息（简化版）
        
        Args:
            subscription_data: 订阅数据
        
        Returns:
            bool: 发送是否成功
        """
        # 构建取消订阅消息
        if isinstance(subscription_data, dict):
            unsubscribe_data = subscription_data.copy()
            if "method" in unsubscribe_data:
                unsubscribe_data["method"] = "unsubscribe"
        else:
            unsubscribe_data = subscription_data
        
        # 发送取消订阅消息
        return self.send(unsubscribe_data)
    
    def is_connected(self):
        """
        检查WebSocket是否已连接
        
        Returns:
            bool: 连接状态
        """
        with self._ws_lock:
            return self._ws_connected
    
    def set_idle_timeout(self, timeout):
        """
        设置闲置超时时间
        
        Args:
            timeout: 超时时间（秒），0表示禁用闲置断开
        """
        with self._ws_lock:
            self.idle_timeout = timeout
            logger.info(f"WebSocket闲置超时已设置为{timeout}秒")
            
            # 如果已连接，重置计时器
            if self._ws_connected:
                self._reset_idle_timer()


def create_hyperliquid_ws_manager(env="mainnet", on_message=None, idle_timeout=60):
    """
    创建Hyperliquid WebSocket管理器
    
    Args:
        env: 环境，"mainnet"或"testnet"
        on_message: 消息处理回调函数
        idle_timeout: 闲置超时时间（秒）
        
    Returns:
        WebSocketManager: WebSocket管理器实例
    """
    ws_url = f"wss://{'dev-' if env == 'testnet' else ''}api.hyperliquid.xyz/ws"
    return WebSocketManager(
        url=ws_url,
        on_message=on_message,
        idle_timeout=idle_timeout
    )


# 网络连接检查函数
def check_internet_connection(host="8.8.8.8", port=53, timeout=3):
    """
    检查互联网连接是否可用
    
    Args:
        host: 要连接的主机
        port: 要连接的端口
        timeout: 超时时间（秒）
        
    Returns:
        bool: 连接是否可用
    """
    import socket
    
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception as e:
        logger.debug(f"网络连接检查失败: {str(e)}")
        return False


def check_api_availability(url, timeout=5):
    """
    检查API是否可用
    
    Args:
        url: API URL
        timeout: 超时时间（秒）
        
    Returns:
        bool: API是否可用
    """
    import requests
    
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except Exception as e:
        logger.debug(f"API可用性检查失败: {str(e)}")
        return False