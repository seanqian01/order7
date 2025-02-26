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
    :param alert_data: TradingView信号数据，包含以下字段：
        - scode: 交易对代码
        - action: 交易方向 ('buy'/'sell')
        - price: 交易价格
        - contractType: 合约类型
    :return: bool 交易是否成功
    """
    try:
        logger.info(f"开始处理Hyperliquid交易信号: {alert_data.scode} {alert_data.action} @ {alert_data.price}")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 验证交易对是否存在且活跃
        contract_config = trader.get_contract_config(alert_data.scode)
        if not contract_config:
            logger.error(f"交易对 {alert_data.scode} 不存在或未激活")
            return False
            
        # 标准化交易方向
        side = alert_data.action.lower()
        if side not in ['buy', 'sell']:
            logger.error(f"无效的交易方向: {side}")
            return False
            
        # 获取账户信息，检查是否有足够的资金
        account_info = trader.get_account_info()
        if account_info["status"] != "success":
            logger.error(f"获取账户信息失败: {account_info.get('error')}")
            return False
            
        # 计算建议仓位大小（风险1%）
        position_calc = trader.calculate_position_size(
            symbol=alert_data.scode,
            price=float(alert_data.price),
            risk_percentage=1
        )
        
        if position_calc["status"] != "success":
            logger.error(f"计算仓位失败: {position_calc.get('error')}")
            return False
            
        position_size = position_calc["position_size"]
        
        # 检查是否满足最小下单数量
        min_size = float(contract_config["min_size"])
        if position_size < min_size:
            logger.warning(f"计算的仓位 {position_size} 小于最小下单数量 {min_size}，将使用最小下单数量")
            position_size = min_size
            
        # 根据size_precision进行数量精度调整
        position_size = round(position_size, contract_config["size_precision"])
        
        # 下单前检查是否有反向持仓
        positions = trader.get_positions([alert_data.scode])
        if positions["status"] == "success" and positions["positions"]:
            current_position = positions["positions"].get(alert_data.scode)
            if current_position:
                current_size = current_position["size"]
                if (side == "buy" and current_size < 0) or (side == "sell" and current_size > 0):
                    logger.info(f"检测到反向持仓，先平掉现有仓位")
                    close_result = trader.close_position(alert_data.scode)
                    if close_result["status"] != "success":
                        logger.error(f"平仓失败: {close_result.get('error')}")
                        return False
        
        # 执行下单
        order_response = trader.place_order(
            symbol=alert_data.scode,
            side=side,
            quantity=position_size,
            price=float(alert_data.price),
            order_type="LIMIT"
        )
        
        if order_response["status"] == "success":
            order_info = order_response["response"]
            logger.info(f"Hyperliquid下单成功: 订单号={order_info.get('order_id')}, "
                       f"交易对={alert_data.scode}, 方向={side}, "
                       f"数量={position_size}, 价格={alert_data.price}")
            return True
        else:
            logger.error(f"Hyperliquid下单失败: {order_response.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"处理Hyperliquid交易信号时发生错误: {str(e)}", exc_info=True)
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
