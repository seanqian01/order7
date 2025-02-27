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
from alert.models import Exchange as ExchangeModel, ContractCode, OrderRecord
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
            
            # 初始化Info和Exchange对象
            self.info = Info(self.api_url)
            self.exchange = Exchange(
                self.account,
                self.api_url,
                account_address=self.wallet_address
            )
            
            # 获取交易所实例
            self.exchange_instance = None  # Initialize as None, will be loaded lazily
            
            # WebSocket相关
            self._ws = None
            self._ws_connected = False
            self._ws_lock = threading.Lock()
            self._ws_thread = None
            self._ws_should_run = False
            
            logger.info(f"HyperliquidTrader initialized in {self.env} environment")
            logger.debug(f"Hyperliquid API已初始化 ({self.env})")
            
        except Exception as e:
            logger.error(f"Error initializing HyperliquidTrader: {str(e)}")
            raise

    def get_exchange_instance(self):
        """
        Lazily get the exchange instance
        """
        if self.exchange_instance is None:
            try:
                self.exchange_instance = ExchangeModel.objects.get(code='HYPERLIQUID')
            except ExchangeModel.DoesNotExist:
                logger.error("HYPERLIQUID exchange not found in database")
        return self.exchange_instance

    def _ensure_ws_connection(self):
        """
        确保WebSocket连接已建立，仅在需要时建立连接
        """
        with self._ws_lock:
            if not self._ws_connected and not self._ws_thread:
                logger.debug("正在按需建立WebSocket连接")
                self._ws_should_run = True
                self._ws_thread = threading.Thread(target=self._ws_connect)
                self._ws_thread.daemon = True
                self._ws_thread.start()
                
                # 等待连接建立或超时
                timeout = 5  # 5秒超时
                start_time = time.time()
                while not self._ws_connected and time.time() - start_time < timeout:
                    time.sleep(0.1)
                
                if not self._ws_connected:
                    logger.warning("WebSocket连接未能在预期时间内建立，将继续执行")

    def _ws_connect(self):
        """
        建立WebSocket连接
        """
        try:
            logger.debug(f"正在连接WebSocket: wss://{'dev-' if self.env == 'testnet' else ''}api.hyperliquid.xyz/ws")
            self._ws = websocket.WebSocketApp(
                f"wss://{'dev-' if self.env == 'testnet' else ''}api.hyperliquid.xyz/ws",
                on_open=self._on_ws_open,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close
            )
            self._ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=30, ping_timeout=10, skip_utf8_validation=True)
        except Exception as e:
            logger.error(f"WebSocket连接出错: {str(e)}")
            self._ws_connected = False

    def _on_ws_open(self, ws):
        """WebSocket连接建立时的回调"""
        with self._ws_lock:
            self._ws_connected = True
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
    def place_order(self, symbol: str, side: str, quantity: int, price: float, 
                     position_type: str = "open", leverage: int = None, reduce_only: bool = False):
        """
        下限价单
        :param symbol: 交易对名称，例如 "HYPE-USDC"
        :param side: 交易方向，"buy"（做多）或"sell"（做空）
        :param quantity: 交易数量（正整数）
                        - 开仓：quantity > 0
                          * buy: 开多单，持仓量为 +quantity
                          * sell: 开空单，持仓量为 -quantity
                        - 平仓：quantity > 0
                          * buy: 平空单（买入平空，减少负的持仓量）
                          * sell: 平多单（卖出平多，减少正的持仓量）
        :param price: 交易价格
        :param position_type: 仓位类型，"open"（开仓）或"close"（平仓）
        :param leverage: 杠杆倍数，如果不指定则使用默认杠杆
        :param reduce_only: 是否只减仓，设置为 True 时订单只会减少持仓
        :return: 下单结果
        """
        try:
            # 尝试建立WebSocket连接，但连接失败不影响下单
            self._ensure_ws_connection()
            
            # 检查订单最小价值
            order_value = quantity * price
            if order_value < 10:
                return {
                    "status": "error",
                    "error": f"订单价值（{order_value:.2f} USDC）低于交易所最小要求（10 USDC）"
                }
            
            # 设置杠杆
            actual_leverage = leverage if leverage is not None else self.default_leverage
            
            # 确保数量为正数
            if quantity <= 0:
                return {
                    "status": "error",
                    "error": "交易数量必须为正数"
                }
            
            # 获取当前持仓信息
            current_positions = self.get_positions()
            if current_positions["status"] != "success":
                logger.error("无法获取当前持仓信息")
                return {
                    "status": "error",
                    "error": "无法获取当前持仓信息"
                }
                
            # 检查平仓操作的持仓情况
            if position_type == "close":
                # 检查是否有对应方向的持仓
                symbol_position = current_positions["positions"].get(symbol, {})
                position_size = float(symbol_position.get("size", 0))
                
                # 如果没有持仓或持仓方向与平仓方向不匹配，返回错误
                if position_size == 0:
                    return {
                        "status": "error",
                        "error": "没有可平仓的持仓"
                    }
                elif (position_size > 0 and side.lower() != "sell") or \
                     (position_size < 0 and side.lower() != "buy"):
                    return {
                        "status": "error",
                        "error": "平仓方向与持仓方向不匹配"
                    }
            
            # 生成订单ID
            import time
            cloid = Cloid.from_int(int(time.time() * 1000))  # 使用时间戳作为订单ID
            
            # 获取交易对的基础币种
            coin = symbol.split('-')[0] if '-' in symbol else symbol
            
            # 记录订单信息
            direction = "多" if side.lower() == "buy" else "空"
            action = "开仓" if position_type == "open" else "平仓"
            logger.info(f"准备{action}{direction}单: {quantity}张 @ {price} USDC")
            logger.info(f"订单参数: leverage={actual_leverage}, reduce_only={reduce_only}")
                
            # 发送订单
            try:
                response = self.exchange.order(
                    coin,  # 交易对，如 "HYPE"
                    side.lower() == "buy",  # is_buy
                    quantity,  # sz
                    price,  # limit_px
                    {"limit": {"tif": "Gtc"}},  # order_type
                    cloid=cloid,  # 可选的客户端订单ID
                    reduce_only=reduce_only  # 是否只减仓
                )
                logger.info(f"订单响应: {response}")
                
                if response.get("status") == "ok":
                    # 检查是否有错误信息
                    order_statuses = response.get("response", {}).get("data", {}).get("statuses", [])
                    if order_statuses and "error" in order_statuses[0]:
                        error_msg = order_statuses[0]["error"]
                        logger.error(f"下单失败: {error_msg}")
                        return {
                            "status": "error",
                            "error": error_msg
                        }
                    
                    # 从响应中获取订单ID
                    order_id = None
                    if order_statuses:
                        status = order_statuses[0]
                        if "resting" in status:
                            order_id = status["resting"]["oid"]
                        elif "filled" in status:
                            order_id = status["filled"]["oid"]
                    
                    if not order_id:
                        logger.error("下单成功但未获取到订单ID")
                        return {
                            "status": "error",
                            "error": "下单成功但未获取到订单ID"
                        }
                    
                    return {
                        "status": "success",
                        "response": response,
                        "order_info": {
                            "symbol": symbol,
                            "side": side,
                            "quantity": quantity,
                            "price": price,
                            "reduce_only": reduce_only,
                            "position_type": position_type,
                            "direction": direction,
                            "cloid": str(cloid),
                            "order_id": order_id
                        }
                    }
                else:
                    return {
                        "status": "error",
                        "error": response.get("error", "Unknown error")
                    }
                    
            except Exception as e:
                logger.error(f"发送订单时出错: {str(e)}")
                return {
                    "status": "error",
                    "error": str(e)
                }
                
        except Exception as e:
            logger.error(f"下单过程中出错: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

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
                position_type="close"
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

    def cancel_order_by_id(self, symbol: str, order_id: int):
        """
        通过订单ID撤单
        :param symbol: 交易对名称，例如 "HYPE-USDC"
        :param order_id: 订单ID（oid）
        :return: 撤单结果
        """
        try:
            # 获取资产ID
            coin = symbol.split('-')[0] if '-' in symbol else symbol
            
            # 构造撤单请求
            # SDK的cancel方法需要coin和order_id，但order_id必须是数字类型
            order_id_int = int(order_id)  # 确保order_id是整数
            logger.info(f"发送撤单请求: coin={coin}, order_id={order_id_int}")
            
            # 使用SDK的cancel方法
            response = self.exchange.cancel(coin, order_id_int)
            logger.info(f"撤单响应: {response}")
            
            # 检查响应
            if response is None:
                error_msg = "撤单请求无响应"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": error_msg
                }
                
            # SDK的响应格式处理
            if isinstance(response, dict):
                if "error" not in response:
                    return {
                        "status": "success",
                        "response": response
                    }
                else:
                    error_msg = response.get("error", str(response))
                    logger.error(f"撤单失败: {error_msg}")
                    return {
                        "status": "error",
                        "error": error_msg
                    }
            else:
                # 如果响应不是字典，说明可能是成功的
                return {
                    "status": "success",
                    "response": response
                }
                
        except Exception as e:
            error_msg = f"撤单过程中出错: {str(e)}"
            logger.error(error_msg)
            logger.exception(e)  # 记录完整的异常堆栈
            return {
                "status": "error",
                "error": error_msg
            }
            
    def cancel_order_by_cloid(self, symbol: str, cloid: str):
        """
        通过客户端订单ID撤单
        :param symbol: 交易对名称，例如 "HYPE-USDC"
        :param cloid: 客户端订单ID
        :return: 撤单结果
        """
        try:
            # 获取资产ID
            coin = symbol.split('-')[0] if '-' in symbol else symbol
            
            # 发送撤单请求
            response = self.exchange.cancel_by_cloid(coin, cloid)
            logger.info(f"撤单响应: {response}")
            
            if response.get("status") == "ok":
                return {
                    "status": "success",
                    "response": response
                }
            else:
                return {
                    "status": "error",
                    "error": response.get("error", "Unknown error")
                }
                
        except Exception as e:
            logger.error(f"撤单过程中出错: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
            
    def cancel_all_orders(self, symbol: str = None):
        """
        撤销所有订单
        :param symbol: 可选，交易对名称。如果不指定，则撤销所有交易对的订单
        :return: 撤单结果
        """
        try:
            # 获取当前未成交订单
            orders = self.get_orders("S")  # 获取当天订单
            if orders["status"] != "success":
                return {
                    "status": "error",
                    "error": "获取订单列表失败"
                }
                
            cancel_results = []
            for order in orders["orders"]:
                # 如果指定了symbol，只撤销该symbol的订单
                if symbol and order["symbol"] != symbol:
                    continue
                    
                # 只撤销未完全成交的订单
                if order["status"] in ["NEW", "PARTIALLY_FILLED"]:
                    result = self.cancel_order_by_id(order["symbol"], order["order_id"])
                    cancel_results.append({
                        "symbol": order["symbol"],
                        "order_id": order["order_id"],
                        "result": result
                    })
            
            return {
                "status": "success",
                "results": cancel_results
            }
                
        except Exception as e:
            logger.error(f"批量撤单过程中出错: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def place_order_with_management(self, symbol: str, side: str, quantity: float, 
                              price: float = None, position_type: str = "open",
                              order_type: str = "limit", reduce_only: bool = False) -> dict:
        """
        下单并进行订单管理
        :param symbol: 交易对名称，例如 "BTC-USDC"
        :param side: 买卖方向，"buy" 或 "sell"
        :param quantity: 数量
        :param price: 价格，市价单可不传
        :param position_type: 持仓类型，"open" 或 "close"
        :param order_type: 订单类型，"limit" 或 "market"
        :param reduce_only: 是否只减仓
        :return: 下单结果
        """
        try:
            # 下单
            order_result = self.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                position_type=position_type,
                order_type=order_type,
                reduce_only=reduce_only
            )
            
            if order_result["status"] != "success":
                return order_result
                
            # 记录订单信息
            order_info = order_result["order_info"]
            order_record = OrderRecord.objects.create(
                order_id=order_info["order_id"],
                cloid=order_info.get("cloid"),
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=price if price else 0,
                quantity=quantity,
                position_type=position_type,
                status="SUBMITTED"
            )
            
            # 启动订单监控线程
            from alert.core.ordertask import order_monitor
            monitor_thread = threading.Thread(
                target=order_monitor.monitor_order,
                args=(order_record.id,)
            )
            monitor_thread.daemon = True  # 设置为守护线程
            monitor_thread.start()
            
            return {
                "status": "success",
                "order_info": order_info,
                "record_id": order_record.id
            }
            
        except Exception as e:
            logger.error(f"下单管理过程中出错: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }