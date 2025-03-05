from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from alert.models import stra_Alert, TimeCycle, ContractCode, OrderRecord
from alert.trade.hyperliquid_api import HyperliquidTrader
import json
from rest_framework.response import Response
from rest_framework import status
import logging
import time
from alert.core.ordertask import order_monitor
import threading
from alert.trade.hyper_order import place_hyperliquid_order
from alert.view.filter_signal import filter_trade_signal

logger = logging.getLogger(__name__)


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

                # 确保合约类型是整数
                alert_contractType = int(alert_contractType)
                logger.info(f"处理交易信号: symbol={alert_symbol}, action={alert_action}, contractType={alert_contractType}, price={alert_price}")

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
                    time_circle=time_circle_instance
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
