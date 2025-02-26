from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
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
        :param wallet_address: 钱包地址
        :param api_secret: API密钥
        """
        try:
            env = settings.HYPERLIQUID_CONFIG["env"]
            self.env_config = settings.HYPERLIQUID_CONFIG[env]
            
            self.wallet_address = wallet_address or self.env_config["wallet_address"]
            self.api_secret = api_secret or self.env_config["api_secret"]
            self.default_leverage = settings.HYPERLIQUID_CONFIG["default_leverage"]
            
            self.info = Info(self.env_config["api_url"])
            self.exchange = Exchange(self.env_config["api_url"])
            
            # 获取交易所实例
            try:
                self.exchange_instance = ExchangeModel.objects.get(code='HYPERLIQUID')
            except ExchangeModel.DoesNotExist:
                logger.error("HYPERLIQUID exchange not found in database")
                self.exchange_instance = None
            
            logger.info(f"HyperliquidTrader initialized in {env} environment")
        except Exception as e:
            logger.error(f"Error initializing HyperliquidTrader: {str(e)}")
            raise

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

    def place_order(self, symbol, side, quantity, price=None, order_type="LIMIT"):
        """
        下单函数
        :param symbol: 交易对
        :param side: 方向 (buy/sell)
        :param quantity: 数量
        :param price: 价格（市价单可不传）
        :param order_type: 订单类型 (LIMIT/MARKET)
        :return: 订单响应
        """
        try:
            # 转换TradingView的买卖方向到Hyperliquid的格式
            hl_side = "B" if side.lower() == "buy" else "S"
            
            # 确保数量为正数
            quantity = abs(float(quantity))
            
            # 如果提供了价格，确保它是float类型
            if price is not None:
                price = float(price)
            
            # 构建订单参数
            order_params = {
                "coin": symbol,
                "is_buy": hl_side == "B",
                "sz": quantity,
                "reduce_only": False,
                "leverage": self.default_leverage
            }
            
            if order_type == "LIMIT" and price is not None:
                order_params["limit_px"] = price
            
            # 发送订单
            if order_type == "MARKET":
                response = self.exchange.market_order(**order_params)
            else:
                response = self.exchange.limit_order(**order_params)
            
            logger.info(f"Order placed successfully on {self.env_config['env']}: {response}")
            return {
                "status": "success",
                "order_id": response.get("order_id"),
                "response": response
            }
            
        except Exception as e:
            error_msg = f"Error placing order on {self.env_config['env']}: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }

    @timeout_handler
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

    @timeout_handler
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

    def calculate_position_size(self, symbol, price, risk_percentage=1):
        """
        计算仓位大小
        :param symbol: 交易对
        :param price: 当前价格 (USDC)
        :param risk_percentage: 账户风险百分比（默认1%）
        :return: 建议的仓位大小
        """
        try:
            account_info = self.get_account_info()
            if account_info["status"] != "success":
                raise Exception("Failed to get account info")

            account_value = Decimal(str(account_info["account_info"]))
            risk_amount = account_value * Decimal(str(risk_percentage)) / Decimal('100')
            
            # 计算合约数量（根据账户价值和风险比例）
            position_size = risk_amount / Decimal(str(price))
            
            # 向下取整到合适的精度
            position_size = float(position_size.quantize(Decimal('0.001')))
            
            return {
                "status": "success",
                "position_size": position_size,
                "account_value": float(account_value),
                "risk_amount": float(risk_amount)
            }
            
        except Exception as e:
            error_msg = f"Error calculating position size: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }

    def close_position(self, symbol):
        """
        关闭指定交易对的持仓
        :param symbol: 交易对
        :return: 关闭结果
        """
        try:
            position = self.get_position(symbol)
            if position["status"] != "success":
                raise Exception("Failed to get position info")

            if not position["position"]:
                return {
                    "status": "success",
                    "message": "No position to close"
                }

            pos = position["position"]
            side = "sell" if pos["size"] > 0 else "buy"
            quantity = abs(float(pos["size"]))

            close_order = self.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET"
            )

            return close_order

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
                order_symbol = order.get("coin")
                
                # 过滤交易对
                if symbol and order_symbol.upper() != symbol.upper():
                    continue
                    
                # 获取合约配置
                contract_config = self.get_contract_config(order_symbol)
                price_precision = contract_config.get("price_precision", 5)
                size_precision = contract_config.get("size_precision", 0)
                
                formatted_order = {
                    "order_id": order.get("oid"),
                    "symbol": order_symbol,
                    "side": "BUY" if order.get("side", 0) > 0 else "SELL",
                    "price": round(float(order.get("px", 0)), price_precision),
                    "size": round(float(order.get("sz", 0)), size_precision),
                    "status": "PENDING",
                    "type": order.get("orderType", "LIMIT"),
                    "time": datetime.datetime.fromtimestamp(order_time / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                    "filled_size": round(float(order.get("filled", 0)), size_precision),
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
                            "symbol": order_symbol,
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