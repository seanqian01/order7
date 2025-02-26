from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from alert.models import stra_Alert, TimeCycle
from alert.trade.hyperliquid_api import HyperliquidTrader
import json
from rest_framework.response import Response
from rest_framework import status
import logging
import time

logger = logging.getLogger(__name__)

def filter_trade_signal(alert_data):
    # 获取当前信号的scode和action
    scode = alert_data.scode
    action = alert_data.action
    time_circle = alert_data.time_circle

    # 查询数据库中相同scode的之前一个信号，按照created_at倒序排列
    previous_signal = stra_Alert.objects.filter(scode=scode, time_circle=time_circle,
                                                created_at__lt=alert_data.created_at).order_by(
        '-created_at').first()

    # 如果找到之前一个信号，比较它们的action
    if previous_signal and previous_signal.action == action:
        # 如果两个信号的action相同，则将当前信号标记为无效
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'Invalid trade signal, 当前信号无效, 请忽略'})

    # 如果没有找到之前一个信号，或者两个信号的action不同，将当前信号标记为有效
    alert_data.status = True
    alert_data.save()

    return Response(status=status.HTTP_200_OK, data={'message': 'Valid trade signal, 当前信号有效, 请处理'})


def place_hyperliquid_order(alert_data):
    """
    处理Hyperliquid交易信号
    :param alert_data: TradingView信号数据
    :return: bool 交易是否成功
    """
    try:
        logger.info(f"收到Hyperliquid交易信号: {alert_data.__dict__}")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 获取当前持仓
        position_result = trader.get_position(alert_data.symbol)
        if position_result["status"] != "success":
            logger.info(f"获取持仓信息失败: {position_result.get('error')}")
            return False
            
        current_position = position_result.get("position")
        logger.info(f"当前持仓信息: {current_position}")
        
        # 判断开平仓
        reduce_only = False
        if current_position:
            current_size = current_position.get("size", 0)
            logger.info(f"当前持仓大小: {current_size}")
            
            # 判断是否需要平仓
            # 如果当前是多仓(size > 0)且收到sell信号，或者当前是空仓(size < 0)且收到buy信号
            if (current_size > 0 and alert_data.action == "sell") or \
               (current_size < 0 and alert_data.action == "buy"):
                reduce_only = True
                quantity = abs(current_size)
                logger.info(f"执行平仓操作: 方向={alert_data.action}, 数量={quantity}")
            else:
                # 同向加仓或反向开仓
                size_result = trader.calculate_position_size(
                    symbol=alert_data.symbol,
                    price=float(alert_data.price),
                    risk_percentage=1
                )
                if size_result["status"] != "success":
                    logger.info(f"计算仓位大小失败: {size_result.get('error')}")
                    return False
                quantity = size_result["position_size"]
                logger.info(f"计算新开仓数量: {quantity}, 方向={alert_data.action}")
        else:
            # 无持仓，开新仓
            size_result = trader.calculate_position_size(
                symbol=alert_data.symbol,
                price=float(alert_data.price),
                risk_percentage=1
            )
            if size_result["status"] != "success":
                logger.info(f"计算仓位大小失败: {size_result.get('error')}")
                return False
            quantity = size_result["position_size"]
            logger.info(f"首次开仓: 方向={alert_data.action}, 数量={quantity}")
        
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
            
            # 检查订单状态
            if response_data.get("status") == "ok":
                statuses = response_data.get("response", {}).get("data", {}).get("statuses", [])
                logger.info(f"订单状态: {statuses}")
                
                if statuses:
                    status = statuses[0]
                    if "resting" in status:
                        logger.info(f"限价单已成功挂单: {order_info}")
                        return True
                    elif "filled" in status:
                        logger.info(f"订单已立即成交: {order_info}")
                        return True
                    elif "error" in status:
                        if "Order price cannot be more than 95% away from the reference price" in status["error"]:
                            logger.warning(f"委托价格超出范围: {status['error']}")
                        else:
                            logger.error(f"订单出错: {status['error']}")
                        return False
                    else:
                        logger.warning(f"未知的订单状态: {status}")
                        return False
                else:
                    logger.info("下单响应中没有状态信息")
                    return False
            else:
                logger.warning(f"下单失败，响应状态异常: {response_data}")
                return False
        else:
            logger.warning(f"Hyperliquid下单失败: {order_response.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"处理Hyperliquid交易信号时发生错误: {str(e)}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return False


@csrf_exempt
def webhook(request, local_secret_key="senaiqijdaklsdjadhjaskdjadkasdasdasd"):
    if request.method == 'POST':
        # 从POST请求中获取JSON数据
        data = request.body.decode('utf-8')
        if data:
            # 解析JSON数据并存储到数据库中
            json_data = json.loads(data)
            # 从字典中获取payload字段的值
            secretkey = json_data.get('secretkey')
            # 先判断key是否正确
            if secretkey == local_secret_key:
                print("signal receive ok")
                alert_title1 = json_data.get('alert_title')
                alert_symbol = json_data.get('symbol')
                alert_scode = json_data.get('scode')
                alert_contractType = json_data.get('contractType')
                alert_price = json_data.get('price')
                alert_action = json_data.get('action')
                time_circle_name = json_data.get('time_circle')  # 获取时间周期名称

                # 查询或创建对应的 TimeCycle 实例
                time_circle_instance, created = TimeCycle.objects.get_or_create(name=time_circle_name)

                trading_view_alert_data = stra_Alert(
                    alert_title=alert_title1,
                    symbol=alert_symbol,
                    scode=alert_scode,
                    contractType=alert_contractType,
                    price=alert_price,
                    action=alert_action,
                    created_at=timezone.now(),
                    time_circle=time_circle_instance  # 将 time_circle 字段设置为对应的 TimeCycle 实例
                )
                trading_view_alert_data.save()

                # 调用过滤函数
                response = filter_trade_signal(trading_view_alert_data)

                # 根据 HTTP 状态码判断信号有效性
                if response.status_code == status.HTTP_200_OK:
                    # 信号有效，执行下单函数
                    if trading_view_alert_data.contractType == 3:  # 虚拟货币
                        success = place_hyperliquid_order(trading_view_alert_data)
                        if success:
                            return HttpResponse('交易信号有效并已在Hyperliquid执行', status=200)
                        else:
                            return HttpResponse('交易信号有效但在Hyperliquid执行失败', status=500)
                    else:
                        return HttpResponse('交易信号有效但不是Hyperliquid渠道', status=200)
                else:
                    # 信号无效，不执行任何操作
                    return HttpResponse(response.data['message'], status=response.status_code)

            else:
                return HttpResponse('信号无效请重试', status=300)
    return HttpResponse('没有数据接收到', status=400)
