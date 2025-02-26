from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import Cloid
from eth_account import Account
from eth_account.signers.local import LocalAccount
from django.conf import settings
import logging
from decimal import Decimal
import requests
from requests.exceptions import Timeout
from functools import wraps
import time
import json
import datetime
from alert.models import Exchange as ExchangeModel, ContractCode
import websocket
import threading
import ssl

logger = logging.getLogger(__name__)

def timeout_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} 执行耗时: {time.time() - start_time:.2f}秒")
            return result
        except requests.Timeout:
            logger.error(f"{func.__name__} 请求超时")
            return {"status": "error", "error": "请求超时"}
        except Exception as e:
            logger.error(f"{func.__name__} 发生错误: {str(e)}")
            return {"status": "error", "error": str(e)}
    return wrapper

class HyperliquidTrader:
    def __init__(self, wallet_address=None, api_secret=None):
        """
        初始化交易接口
        """
        try:
            # 配置
            self.env = settings.HYPERLIQUID_CONFIG.get('env', 'mainnet')
            env_config = settings.HYPERLIQUID_CONFIG.get(self.env, {})
            
            self.api_url = env_config.get('api_url')
            self.wallet_address = wallet_address or env_config.get('wallet_address')
            self.api_secret = api_secret or env_config.get('api_secret')
            self.default_leverage = settings.HYPERLIQUID_CONFIG.get('default_leverage', 1)
            
            # 创建钱包对象
            self.account: LocalAccount = Account.from_key(self.api_secret)
            if self.wallet_address == "":
                self.wallet_address = self.account.address
            
            self.info = Info(self.api_url)
            # 使用钱包对象初始化交易所
            self.exchange = Exchange(
                self.account,
                self.api_url,
                account_address=self.wallet_address
            )
            
            # 获取交易所实例
            try:
                self.exchange_instance = ExchangeModel.objects.get(code='HYPERLIQUID')
            except ExchangeModel.DoesNotExist:
                logger.error("HYPERLIQUID exchange not found in database")
                self.exchange_instance = None
            
            logger.info(f"HyperliquidTrader initialized in {self.env} environment")
            logger.info(f"Using API URL: {self.api_url}")
            logger.info(f"Using wallet address: {self.wallet_address}")
            logger.info(f"Using API wallet address: {self.account.address}")
            
            # WebSocket连接状态
            self._ws_connected = False
            self._ws_lock = threading.Lock()
            self._init_websocket()
            
        except Exception as e:
            logger.error(f"Error initializing HyperliquidTrader: {str(e)}")
            raise

    def _init_websocket(self):
        """
        初始化WebSocket连接
        """
        try:
            with self._ws_lock:
                if not self._ws_connected:
                    # 关闭可能存在的旧连接
                    if hasattr(self, '_ws'):
                        try:
                            self._ws.close()
                        except:
                            pass
                    
                    # 创建新的WebSocket连接
                    ws_url = f"wss://{'dev-' if self.env == 'testnet' else ''}api.hyperliquid.xyz/ws"
                    logger.info(f"正在连接WebSocket: {ws_url}")
                    
                    # 创建连接事件
                    self._ws_connected_event = threading.Event()
                    
                    # 创建WebSocket连接
                    self._ws = websocket.WebSocketApp(
                        ws_url,
                        on_open=self._on_ws_open,
                        on_close=self._on_ws_close,
                        on_error=self._on_ws_error,
                        on_message=self._on_ws_message
                    )
                    
                    # 在后台线程中运行WebSocket，调整ping/pong参数
                    self._ws_thread = threading.Thread(target=lambda: self._ws.run_forever(
                        sslopt={"cert_reqs": ssl.CERT_NONE},
                        ping_interval=10,  # 减少ping间隔
                        ping_timeout=5,    # 减少ping超时
                        skip_utf8_validation=True
                    ))
                    self._ws_thread.daemon = True
                    self._ws_thread.start()
                    
                    # 等待连接建立
                    if self._ws_connected_event.wait(timeout=10):
                        logger.info("WebSocket连接成功建立")
                        self._subscribe_market_data()
                    else:
                        logger.warning("WebSocket连接超时，将继续执行订单")
                        
        except Exception as e:
            logger.warning(f"初始化WebSocket连接失败: {str(e)}")
            import traceback
            logger.warning(f"Traceback:\n{traceback.format_exc()}")

    def _on_ws_open(self, ws):
        """WebSocket连接建立时的回调"""
        with self._ws_lock:
            self._ws_connected = True
        self._ws_connected_event.set()  # 设置连接成功事件
        logger.info("WebSocket连接已建立")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket连接关闭时的回调"""
        with self._ws_lock:
            self._ws_connected = False
        logger.info("WebSocket连接已关闭")

    def _on_ws_error(self, ws, error):
        """WebSocket错误时的回调"""
        logger.warning(f"WebSocket错误: {error}")

    def _on_ws_message(self, ws, message):
        """WebSocket消息处理"""
        try:
            data = json.loads(message)
            logger.debug(f"收到WebSocket消息: {data}")
        except Exception as e:
            logger.warning(f"处理WebSocket消息时出错: {str(e)}")

    def _subscribe_market_data(self):
        """订阅市场数据"""
        try:
            # 构建订阅消息
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "trades",
                    "coins": ["HYPE"]  # 可以根据需要添加其他币种
                }
            }
            
            # 发送订阅请求
            self._ws.send(json.dumps(subscribe_msg))
            logger.info("已发送市场数据订阅请求")
        except Exception as e:
            logger.warning(f"订阅市场数据失败: {str(e)}")

    def _ensure_ws_connection(self):
        """
        确保WebSocket连接正常
        """
        try:
            with self._ws_lock:
                if not self._ws_connected:
                    logger.info("正在重新建立WebSocket连接...")
                    self._init_websocket()
                    if not self._ws_connected:
                        logger.warning("无法建立WebSocket连接，但将继续执行订单")
                else:
                    logger.debug("WebSocket连接正常")
        except Exception as e:
            logger.warning(f"检查WebSocket连接状态时出错: {str(e)}")

    def get_default_symbols(self):
        """
        获取默认交易对列表
        """
        if not self.exchange_instance:
            return []
            
        symbols = ContractCode.objects.filter(
            exchange=self.exchange_instance,
            is_active=True
        ).values_list('symbol', flat=True)
        return list(symbols)

    def get_contract_config(self, symbol):
        """
        从数据库获取合约配置
        :param symbol: 交易对符号
        :return: 合约配置信息
        """
        if not self.exchange_instance:
            return {}
            
        try:
            contract = ContractCode.objects.get(
                exchange=self.exchange_instance,
                symbol=symbol,
                is_active=True
            )
            return {
                "symbol": contract.symbol,
                "name": contract.name,
                "description": contract.description,
                "price_precision": contract.price_precision,
                "size_precision": contract.size_precision,
                "min_size": float(contract.min_size),
                "size_increment": float(contract.size_increment)
            }
        except ContractCode.DoesNotExist:
            logger.warning(f"Contract config not found for symbol: {symbol}")
            return {}

    @timeout_handler
    def place_order(self, symbol: str, side: str, quantity: int, price: float, reduce_only: bool = False):
        """
        下限价单
        :param symbol: 交易对名称，例如 "HYPE-USDC"
        :param side: 交易方向，"buy" 或 "sell"
        :param quantity: 交易数量
        :param price: 限价单价格
        :param reduce_only: 是否为平仓单
        :return: 下单结果
        """
        try:
            # 确保WebSocket连接正常
            self._ensure_ws_connection()
            
            # 规范化价格
            normalized_price = self._normalize_price(symbol, price)
            logger.info(f"Using normalized price: {normalized_price} (original: {price})")
            
            # 检查保证金是否足够（如果不是平仓订单）
            if not reduce_only:
                margin_check = self._check_margin(symbol, quantity, normalized_price)
                if margin_check["status"] != "success":
                    logger.warning(f"保证金检查失败: {margin_check['error']}")
                    return {
                        "status": "error",
                        "error": margin_check["error"]
                    }
                logger.info(f"保证金检查通过: {margin_check}")
            
            # 参数验证
            if not isinstance(symbol, str) or '-' not in symbol:
                error_msg = f"Invalid symbol format: {symbol}. Expected format: COIN-USDC"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }

            # 验证交易方向
            if side.lower() not in ["buy", "sell"]:
                error_msg = f"Invalid side: {side}. Must be 'buy' or 'sell'"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }

            # 检查当前持仓
            position_info = self.get_position(symbol)
            logger.info(f"Current position info: {position_info}")
            
            if position_info.get("status") != "success":
                error_msg = f"Failed to get position info: {position_info.get('error')}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
                
            current_position = position_info.get("position")
            
            # 处理平仓逻辑
            if current_position:
                current_size = current_position.get("size", 0)
                logger.info(f"Current position size: {current_size}")
                
                # 如果是平仓操作
                if (current_size > 0 and side.lower() == "sell") or (current_size < 0 and side.lower() == "buy"):
                    reduce_only = True
                    quantity = abs(current_size)
                    logger.info(f"Closing position: size={quantity}, reduce_only={reduce_only}")
                elif reduce_only:
                    # 如果指定了reduce_only但方向错误
                    if (current_size > 0 and side.lower() == "buy") or (current_size < 0 and side.lower() == "sell"):
                        error_msg = f"Invalid reduce_only order: Cannot {side} when position is {current_size}"
                        logger.error(error_msg)
                        return {
                            "status": "error",
                            "error": error_msg
                        }
            elif reduce_only:
                error_msg = "Cannot place reduce_only order when no position exists"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }

            # 确保数值参数为正确的类型
            try:
                quantity = int(float(quantity))  # 确保数量是整数
                price = float(normalized_price)
                if quantity <= 0 or price <= 0:
                    raise ValueError("Quantity and price must be positive")
                logger.info("Converted numeric parameters:")
                logger.info(f"quantity: {quantity} (type: {type(quantity)})")
                logger.info(f"price: {price} (type: {type(price)})")
            except ValueError as e:
                error_msg = f"Invalid numeric parameters: {str(e)}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
            
            # 从 symbol 中提取币种名称（去掉 -USDC 后缀）
            coin_name = symbol.split('-')[0].upper()  # 确保币种名称大写
            logger.info(f"Extracted coin_name: {coin_name!r} (type: {type(coin_name)})")
            
            # 生成唯一的订单ID
            import uuid
            import random
            cloid = Cloid.from_int(random.randint(1, 2**32-1))  # 使用随机整数生成 Cloid
            logger.info(f"Generated cloid: {cloid!r}")
            
            # 确定买卖方向
            is_buy = side.lower() == "buy"
            logger.info(f"Determined is_buy: {is_buy!r} (type: {type(is_buy)})")
            
            # 检查数量是否小于最小交易量
            min_size = 1
            if quantity < min_size:
                logger.warning(f"Order quantity {quantity} is less than minimum size {min_size}, adjusting to minimum")
                quantity = min_size
            
            try:
                # 构建下单参数
                order_params = {
                    "name": coin_name,
                    "is_buy": is_buy,
                    "sz": quantity,
                    "limit_px": price,
                    "reduce_only": reduce_only,
                    "order_type": {"limit": {"tif": "Gtc"}},
                    "cloid": cloid
                }
                logger.info("Final order parameters:")
                for key, value in order_params.items():
                    logger.info(f"  {key}: {value!r} (type: {type(value)})")
                
                # 使用SDK的order方法下限价单
                try:
                    logger.info("Calling exchange.order with parameters:")
                    logger.info(json.dumps({k: str(v) if isinstance(v, Cloid) else v for k, v in order_params.items()}, indent=2))
                    response = self.exchange.order(**order_params)
                    logger.info(f"Raw API Response: {response!r}")
                    logger.info(f"Response type: {type(response)}")
                    
                    if isinstance(response, (list, tuple)):
                        logger.info(f"Response is sequence type, length: {len(response)}")
                        logger.info(f"Response elements: {[type(x) for x in response]}")
                        
                    if isinstance(response, dict):
                        logger.info(f"Response keys: {list(response.keys())}")
                        
                    # 检查订单状态
                    if response.get("status") == "ok":
                        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
                        logger.info(f"Order statuses: {statuses}")
                        
                        if statuses:
                            status = statuses[0]
                            if "resting" in status:
                                logger.info("Order is resting (placed successfully)")
                                resting_info = status["resting"]
                                logger.info(f"Resting order details: {resting_info}")
                            elif "filled" in status:
                                logger.info("Order was immediately filled")
                                filled_info = status["filled"]
                                logger.info(f"Filled order details: {filled_info}")
                            else:
                                logger.warning(f"Unexpected status: {status}")
                                
                            # 验证订单是否真实存在
                            order_status = self.info.query_order_by_cloid(self.wallet_address, cloid)
                            logger.info(f"Order verification by cloid: {order_status}")
                    else:
                        logger.error(f"Order placement failed with status: {response.get('status')}")
                        
                except Exception as e:
                    logger.error(f"Error during API call: {str(e)}")
                    import traceback
                    logger.error(f"Traceback:\n{traceback.format_exc()}")
                    raise
                
                # 处理响应
                if isinstance(response, str):
                    try:
                        logger.info("Attempting to parse response as JSON string")
                        response = json.loads(response)
                        logger.info(f"Parsed JSON response: {response}")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse response as JSON: {str(e)}")
                        response = {"message": response}
                
                if not isinstance(response, dict):
                    logger.warning(f"Converting non-dict response to dict: {response}")
                    response = {"message": str(response)}
                
                # 检查错误信息
                error_message = response.get("error") or response.get("message")
                if error_message and "success" not in str(error_message).lower():
                    logger.error(f"API returned error: {error_message}")
                    return {
                        "status": "error",
                        "error": str(error_message)
                    }
                
                order_type = "平仓" if reduce_only else "开仓"
                logger.info(f"Limit order placed successfully: symbol={symbol}, side={side}, type={order_type}, "
                        f"quantity={quantity}, price={price}, response={response}")
                
                # 返回成功响应
                return {
                    "status": "success",
                    "response": response,
                    "order_info": {
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity,
                        "price": price,
                        "reduce_only": reduce_only,
                        "cloid": cloid  # 直接传递 Cloid 对象
                    }
                }
            except Exception as e:
                error_msg = f"Error placing limit order: {str(e)}"
                logger.error(error_msg)
                import traceback
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                return {
                    "status": "error",
                    "error": error_msg
                }
        except Exception as e:
            error_msg = f"Error preparing order parameters: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            return {
                "status": "error",
                "error": error_msg
            }

    def _normalize_price(self, symbol: str, price: float) -> float:
        """
        将价格规范化为符合 tick size 的值
        """
        try:
            # 获取市场信息
            market_info = self.info.meta()
            if not market_info or "universe" not in market_info:
                logger.warning("无法获取市场信息，将使用原始价格")
                return price
                
            # 查找对应交易对的信息
            symbol_base = symbol.split('-')[0] if '-' in symbol else symbol
            market_data = None
            for item in market_info["universe"]:
                if item["name"] == symbol_base:
                    market_data = item
                    break
                    
            if not market_data:
                logger.warning(f"无法找到 {symbol} 的市场信息，将使用原始价格")
                return price
                
            # 获取 tick size
            tick_size = float(market_data.get("tick_size", "0.1"))
            logger.info(f"获取到 {symbol} 的 tick_size: {tick_size}")
            
            # 规范化价格
            normalized_price = round(price / tick_size) * tick_size
            
            # 确保价格有正确的小数位数
            sz_decimals = len(str(tick_size).split('.')[-1]) if '.' in str(tick_size) else 0
            if sz_decimals > 0:
                normalized_price = round(normalized_price, sz_decimals)
                
            logger.info(f"价格规范化: 原始价格={price}, tick_size={tick_size}, 规范化后={normalized_price}")
            return normalized_price
            
        except Exception as e:
            logger.error(f"价格规范化失败: {str(e)}")
            return price

    def get_position(self, symbol):
        """
        获取永续合约持仓信息
        :param symbol: 交易对符号，例如 "S"
        :return: 持仓信息，包含：
                - symbol: 合约符号
                - size: 持仓量
                - entry_price: 开仓均价 (USDC)
                - leverage: 杠杆倍数
                - liquidation_price: 清算价格 (USDC)
                - unrealized_pnl: 未实现盈亏 (USDC)
                - margin_used: 已用保证金 (USDC)
                - position_value: 持仓价值 (USDC)
                - return_on_equity: 投资回报率
                - max_leverage: 最大可用杠杆
                - cum_funding: 累计资金费用 (USDC)
        """
        try:
            user_state = self.info.user_state(self.wallet_address)
            if not user_state:
                logger.warning(f"No user state found for {self.wallet_address}")
                return {"status": "success", "position": None}
                
            positions = user_state.get("assetPositions", [])
            
            if isinstance(positions, list):
                for pos in positions:
                    if isinstance(pos, dict) and "position" in pos:
                        position = pos["position"]
                        coin = position.get("coin")
                        if coin and coin.upper() == symbol.upper():
                            # 获取合约配置
                            contract_config = self.get_contract_config(coin)
                            price_precision = contract_config.get("price_precision", 5)
                            size_precision = contract_config.get("size_precision", 0)
                            
                            # 格式化数值
                            entry_price = float(position.get("entryPx", 0))
                            size = float(position.get("szi", 0))
                            
                            return {
                                "status": "success",
                                "position": {
                                    "symbol": coin,
                                    "description": contract_config.get("description", f"{coin} USDC永续"),
                                    "size": round(size, size_precision),
                                    "entry_price": round(entry_price, price_precision),
                                    "leverage": position.get("leverage", {}).get("value", self.default_leverage),
                                    "liquidation_price": round(float(position.get("liquidationPx", 0)), price_precision),
                                    "unrealized_pnl": round(float(position.get("unrealizedPnl", 0)), 2),
                                    "margin_used": round(float(position.get("marginUsed", 0)), 2),
                                    "position_value": round(float(position.get("positionValue", 0)), 2),
                                    "return_on_equity": round(float(position.get("returnOnEquity", 0)), 4),
                                    "max_leverage": position.get("maxLeverage", 0),
                                    "cum_funding": {
                                        "all_time": round(float(position.get("cumFunding", {}).get("allTime", 0)), 4),
                                        "since_open": round(float(position.get("cumFunding", {}).get("sinceOpen", 0)), 4),
                                        "since_change": round(float(position.get("cumFunding", {}).get("sinceChange", 0)), 4)
                                    }
                                }
                            }
            
            return {"status": "success", "position": None}
            
        except Exception as e:
            logger.error(f"Error parsing position data: {str(e)}")
            return {"status": "error", "error": f"Position data parsing error: {str(e)}"}

    def get_positions(self, symbols=None):
        """
        获取多个永续合约的持仓信息
        :param symbols: 交易对符号列表。如果为None，则使用数据库中的活跃交易对
        :return: 持仓信息字典，key为symbol
        """
        if symbols is None:
            symbols = self.get_default_symbols()
            
        positions = {}
        for symbol in symbols:
            pos = self.get_position(symbol)
            if pos["status"] == "success" and pos.get("position"):
                positions[symbol] = pos["position"]
                
        return {
            "status": "success",
            "positions": positions
        }

    @timeout_handler
    def get_account_info(self):
        """
        获取账户信息
        :return: 账户信息，包含：
                - account_info: 账户总值 (USDC)
                - margin_summary: 保证金概要
                - cross_margin_summary: 全仓保证金概要
                - withdrawable: 可提现金额 (USDC)
        """
        try:
            user_state = self.info.user_state(self.wallet_address)
            
            if user_state:
                # 尝试获取不同的余额字段
                account_value = None
                
                # 检查marginSummary
                margin_summary = user_state.get("marginSummary", {})
                if margin_summary:
                    account_value = margin_summary.get("accountValue")
                    
                # 如果marginSummary中没有，检查crossMarginSummary
                if not account_value:
                    cross_margin = user_state.get("crossMarginSummary", {})
                    if cross_margin:
                        account_value = cross_margin.get("accountValue")
                
                # 如果还是没有，检查其他可能的字段
                if not account_value:
                    account_value = user_state.get("withdrawable")
                
                if account_value:
                    return {
                        "status": "success",
                        "account_info": account_value,
                        "margin_summary": margin_summary,
                        "cross_margin_summary": user_state.get("crossMarginSummary", {}),
                        "withdrawable": user_state.get("withdrawable")
                    }
            
            raise Exception("Unable to get account value from user state")
            
        except Exception as e:
            logger.error(f"Error getting account info: {str(e)}")
            return {"status": "error", "error": f"Account info error: {str(e)}"}

    def calculate_position_size(self, symbol: str, price: float, risk_percentage: float = 1.0) -> dict:
        """
        计算仓位大小
        :param symbol: 交易对名称
        :param price: 当前价格
        :param risk_percentage: 风险百分比（占账户总值的百分比）
        :return: 计算结果，包含仓位大小等信息
        """
        try:
            # 获取账户总值
            account_info = self.get_account_info()
            if account_info["status"] != "success":
                return {"status": "error", "error": "Failed to get account value"}

            # 确保账户总值是浮点数
            try:
                account_value = float(account_info["account_info"])
                risk_percentage = float(risk_percentage)
                price = float(price)
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid numeric value: account_value={account_info['account_info']}, "
                           f"risk_percentage={risk_percentage}, price={price}")
                raise ValueError(f"Invalid numeric value: {str(e)}")

            # 计算可用于此次交易的资金（账户总值 * 风险百分比）
            risk_amount = account_value * (risk_percentage / 100)
            logger.info(f"Calculated risk amount: {risk_amount} = {account_value} * ({risk_percentage} / 100)")

            # 计算仓位大小（向下取整到整数）
            position_size = int(risk_amount / price)
            logger.info(f"Calculated position size: {position_size} = int({risk_amount} / {price})")

            # 确保至少为1
            if position_size < 1:
                position_size = 1
                logger.info(f"Adjusted position size to minimum: {position_size}")

            return {
                "status": "success",
                "position_size": position_size,
                "account_value": account_value,
                "risk_amount": risk_amount
            }
            
        except Exception as e:
            error_msg = f"Error calculating position size: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }

    def close_position(self, symbol, price):
        """
        关闭指定交易对的持仓
        :param symbol: 交易对
        :param price: 平仓价格
        :return: 关闭结果
        """
        try:
            # 获取当前持仓
            position = self.get_position(symbol)
            if position["status"] != "success":
                raise Exception("Failed to get position info")

            if not position["position"]:
                return {
                    "status": "success",
                    "message": "No position to close"
                }

            pos = position["position"]
            
            # 确定平仓方向和数量
            side = "sell" if pos["size"] > 0 else "buy"
            quantity = abs(float(pos["size"]))
            
            logger.info(f"Closing position: {symbol} {side} {quantity} @ {price}")
            
            # 使用限价单平仓，使用信号指定的价格
            return self.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_type="LIMIT",
                reduce_only=True
            )

        except Exception as e:
            error_msg = f"Error closing position: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }

    @timeout_handler
    def get_orders(self, symbol=None, start_time=None, end_time=None, status=None):
        """
        获取订单历史
        :param symbol: 交易对符号，如果为None则查询所有
        :param start_time: 开始时间戳（毫秒）
        :param end_time: 结束时间戳（毫秒）
        :param status: 订单状态，可选值：FILLED, CANCELED, PENDING
        :return: 订单列表
        """
        try:
            # 如果没有指定时间范围，默认查询当天
            if not start_time:
                start_time = int(datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
            if not end_time:
                end_time = int(datetime.datetime.now().timestamp() * 1000)
                
            # 获取当前挂单
            current_orders = self.info.user_state(self.wallet_address).get("orders", [])
            # 获取历史成交
            filled_orders = self.info.user_fills(self.wallet_address)
            
            result = []
            
            # 处理当前挂单
            for order in current_orders:
                order_time = int(time.time() * 1000)  # 当前订单使用当前时间
                coin = order.get("coin")  # 从API获取币种代码
                
                # 过滤交易对
                if symbol and coin.upper() != symbol.upper():
                    continue
                    
                # 获取合约配置
                contract_config = self.get_contract_config(coin)
                price_precision = contract_config.get("price_precision", 5)
                size_precision = contract_config.get("size_precision", 0)
                
                formatted_order = {
                    "order_id": order.get("oid"),
                    "symbol": symbol if symbol else coin,  # 优先使用传入的 symbol
                    "side": "BUY" if order.get("side", 0) > 0 else "SELL",
                    "price": round(float(order.get("px", 0)), price_precision),
                    "size": int(float(order.get("sz", 0))),  # 确保 size 是整数
                    "status": "PENDING",
                    "type": order.get("orderType", "LIMIT"),
                    "time": datetime.datetime.fromtimestamp(order_time / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                    "filled_size": int(float(order.get("filled", 0))),  # filled_size 也应该是整数
                    "fee": round(float(order.get("fee", 0)), 8)
                }
                
                if status is None or formatted_order["status"] == status:
                    result.append(formatted_order)
            
            # 处理历史成交
            if filled_orders:
                for order in filled_orders:
                    try:
                        # 确保时间戳是整数
                        order_time = int(float(order.get("time", 0)))
                        if order_time < start_time or order_time > end_time:
                            continue
                            
                        order_symbol = order.get("coin")
                        if symbol and order_symbol.upper() != symbol.upper():
                            continue
                            
                        # 获取合约配置
                        contract_config = self.get_contract_config(order_symbol)
                        price_precision = contract_config.get("price_precision", 5)
                        size_precision = contract_config.get("size_precision", 0)
                        
                        # 解析价格和数量，确保是浮点数
                        price = float(order.get("px", 0))
                        size = float(order.get("sz", 0))
                        fee = float(order.get("fee", 0))
                        
                        formatted_order = {
                            "order_id": order.get("oid"),
                            "symbol": symbol if symbol else order_symbol,  # 优先使用传入的 symbol
                            "side": "BUY" if order.get("side") == "B" else "SELL",
                            "price": round(price, price_precision),
                            "size": round(size, size_precision),
                            "status": "FILLED",
                            "type": "MARKET" if "Market" in order.get("dir", "") else "LIMIT",
                            "time": datetime.datetime.fromtimestamp(order_time / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                            "filled_size": round(size, size_precision),
                            "fee": round(fee, 8),
                            "fee_token": order.get("feeToken", "USDC")
                        }
                        
                        if status is None or formatted_order["status"] == status:
                            result.append(formatted_order)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"无效订单数据: {str(e)}")
                        continue
            
            # 按时间倒序排序
            result.sort(key=lambda x: x["time"], reverse=True)
            return {"status": "success", "orders": result}
            
        except Exception as e:
            logger.error(f"Error getting orders: {str(e)}")
            return {"status": "error", "error": f"Failed to get orders: {str(e)}"}
            
    @timeout_handler
    def cancel_order(self, symbol, order_id):
        """
        撤销订单
        :param symbol: 交易对符号
        :param order_id: 订单ID
        :return: 撤单结果
        """
        try:
            response = self.exchange.cancel_order(
                symbol=symbol,
                order_id=order_id
            )
            
            logger.info(f"Order cancelled successfully: {response}")
            return {
                "status": "success",
                "order_id": order_id,
                "message": "Order cancelled successfully"
            }
            
        except Exception as e:
            error_msg = f"Error cancelling order {order_id}: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
            
    @timeout_handler
    def cancel_all_orders(self, symbol=None):
        """
        撤销所有订单
        :param symbol: 交易对符号，如果为None则撤销所有交易对的订单
        :return: 撤单结果
        """
        try:
            if symbol:
                symbols = [symbol]
            else:
                symbols = self.get_default_symbols()
                
            cancelled = []
            failed = []
            
            for sym in symbols:
                try:
                    response = self.exchange.cancel_all_orders(symbol=sym)
                    cancelled.append(sym)
                except Exception as e:
                    logger.error(f"Error cancelling orders for {sym}: {str(e)}")
                    failed.append(sym)
            
            return {
                "status": "success" if not failed else "partial",
                "cancelled": cancelled,
                "failed": failed
            }
            
        except Exception as e:
            error_msg = f"Error cancelling all orders: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }

    def _check_margin(self, symbol: str, quantity: int, price: float) -> dict:
        """
        检查是否有足够的保证金
        """
        try:
            # 获取账户信息
            account_info = self.info.user_state(self.wallet_address)
            if not account_info:
                return {
                    "status": "error",
                    "error": "无法获取账户信息"
                }
            
            # 获取可用保证金
            available_margin = float(account_info.get("marginSummary", {}).get("accountValue", 0))
            
            # 计算所需保证金（这里使用一个简单的估算）
            required_margin = (price * quantity) / self.default_leverage
            
            logger.info(f"保证金检查: 可用={available_margin}, 需要={required_margin}")
            
            if available_margin < required_margin:
                return {
                    "status": "error",
                    "error": f"保证金不足。需要: {required_margin}, 可用: {available_margin}"
                }
            
            return {
                "status": "success",
                "available_margin": available_margin,
                "required_margin": required_margin
            }
            
        except Exception as e:
            logger.error(f"检查保证金时出错: {str(e)}")
            return {
                "status": "error",
                "error": f"检查保证金失败: {str(e)}"
            }