import logging
from alert.models import ContractCode, OrderRecord
from alert.trade.hyperliquid_api import HyperliquidTrader
from alert.core.ordertask import order_monitor
import threading

logger = logging.getLogger(__name__)

def place_hyperliquid_order(alert_data, quantity=None):
    """
    在Hyperliquid交易所下单
    """
    try:
        logger.info(f"开始处理下单请求: symbol={alert_data.symbol}, action={alert_data.action}, contractType={alert_data.contractType}")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 获取当前持仓
        position_result = trader.get_position(alert_data.symbol)
        if position_result["status"] != "success":
            logger.error(f"获取持仓信息失败: {position_result.get('error')}")
            return False
            
        current_position = position_result.get("position")
        logger.info(f"当前持仓信息: {current_position}")
        
        # 判断开平仓
        reduce_only = False
        
        # 先查询交易对配置
        symbol_base = alert_data.symbol.split('-')[0] if '-' in alert_data.symbol else alert_data.symbol
        logger.info(f"查询交易对配置: symbol_base={symbol_base}, 原始symbol={alert_data.symbol}")
        
        # 查询数据库中的默认下单配置
        contract = ContractCode.objects.filter(
            symbol=symbol_base,
            is_active=True
        ).first()
        
        if not contract:
            logger.error(f"未找到交易对 {symbol_base} 的配置,请先在后台设置默认下单数量")
            return False
            
        logger.info(f"找到交易对配置: symbol={contract.symbol}, default_quantity={contract.default_quantity}")
        
        # 情况1: 有持仓时的处理逻辑
        if current_position:
            current_size = current_position.get("size", 0)
            logger.info(f"当前持仓大小: {current_size}")
            
            # 如果当前是多仓(size > 0)且收到sell信号，或者当前是空仓(size < 0)且收到buy信号
            # 使用当前持仓数量来平仓
            if (current_size > 0 and alert_data.action == "sell") or \
               (current_size < 0 and alert_data.action == "buy"):
                reduce_only = True
                quantity = abs(current_size)
                logger.info(f"有持仓且信号方向相反，执行平仓: 方向={alert_data.action}, 使用持仓数量={quantity}")
            else:
                # 同向加仓，使用默认下单数量
                quantity = float(contract.default_quantity)
                logger.info(f"有持仓且信号方向相同，执行加仓: 方向={alert_data.action}, 使用默认下单数量={quantity}")
        else:
            # 情况2: 无持仓时的处理逻辑
            # 使用数据库中设置的默认下单数量来开仓
            quantity = float(contract.default_quantity)
            logger.info(f"无持仓，执行开仓: 方向={alert_data.action}, 使用默认下单数量={quantity}")
        
        # 下单
        logger.info(f"准备下单: symbol={alert_data.symbol}, action={alert_data.action}, "
                   f"quantity={quantity}, price={alert_data.price}, reduce_only={reduce_only}")
        
        order_response = trader.place_order(
            symbol=alert_data.symbol,
            side=alert_data.action,
            quantity=int(quantity),
            price=float(alert_data.price),
            reduce_only=reduce_only
        )
        
        if order_response["status"] == "success":
            response_data = order_response.get("response", {})
            order_info = order_response.get("order_info", {})
            logger.info(f"下单成功: {order_info}")
            
            # 检查订单状态和订单ID
            if response_data.get("status") == "ok" and order_info.get("order_id"):
                # 创建订单记录
                try:
                    order_record = OrderRecord.objects.create(
                        order_id=str(order_info["order_id"]),  # 确保转换为字符串
                        cloid=order_info.get("cloid"),
                        symbol=alert_data.symbol,
                        side=alert_data.action,
                        order_type="limit",
                        price=alert_data.price,
                        quantity=quantity,
                        position_type="close" if reduce_only else "open",
                        status="SUBMITTED",
                        filled_quantity=0
                    )
                    
                    # 启动订单监控线程
                    monitor_thread = threading.Thread(
                        target=order_monitor.monitor_order,
                        args=(order_record.id,)
                    )
                    monitor_thread.daemon = True
                    monitor_thread.start()
                    
                    logger.info(f"订单已创建并开始监控: order_id={order_info['order_id']}")
                    return True
                    
                except Exception as e:
                    logger.error(f"创建订单记录时出错: {str(e)}")
                    return False
            else:
                logger.error(f"下单成功但未获取到订单ID或状态异常: {order_response}")
                return False
        elif order_response["status"] == "error":
            # 移除重复的警告日志，因为具体错误已经在 hyperliquid_api.py 中记录
            return False, order_response["error"]
        else:
            # 下单失败，记录错误信息
            error_msg = order_response.get("error", "Unknown error")
            logger.warning(f"Hyperliquid下单失败: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"处理Hyperliquid交易信号时发生错误: {str(e)}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False