from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from alert.models import stra_Alert, TimeCycle, ContractCode, OrderRecord
import json
from rest_framework.response import Response
from rest_framework import status
import logging
from alert.core.signal_queue import signal_processor
from alert.core.async_db import async_db_handler

logger = logging.getLogger(__name__)

@csrf_exempt
def webhook(request, local_secret_key="senaiqijdaklsdjadhjaskdjadkasdasdasd"):
    if request.method == 'POST':
        try:
            # 从POST请求中获取JSON数据
            data = request.body.decode('utf-8')
            if not data:
                return HttpResponse('没有数据接收到', status=400)

            # 解析JSON数据
            json_data = json.loads(data)
            secretkey = json_data.get('secretkey')

            # 验证密钥
            if secretkey != local_secret_key:
                return HttpResponse('信号无效请重试', status=300)

            logger.info("信号接收成功，开始处理")

            # 获取信号数据
            alert_title1 = json_data.get('alert_title')
            alert_symbol = json_data.get('symbol')
            alert_scode = json_data.get('scode')
            alert_contractType = int(json_data.get('contractType'))  # 确保合约类型是整数
            alert_price = json_data.get('price')
            alert_action = json_data.get('action')
            time_circle_name = json_data.get('time_circle')

            logger.info(f"处理交易信号: symbol={alert_symbol}, action={alert_action}, contractType={alert_contractType}, price={alert_price}")

            # 查询或创建对应的 TimeCycle 实例
            time_circle_instance, created = TimeCycle.objects.get_or_create(name=time_circle_name)

            # 创建信号对象
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

            # 异步保存信号数据到数据库
            async_db_handler.async_save(trading_view_alert_data)

            # 将信号添加到处理队列
            signal_processor.add_signal(trading_view_alert_data)

            return HttpResponse('信号已接收并加入处理队列', status=200)

        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            return HttpResponse('无效的JSON数据', status=400)
        except Exception as e:
            logger.error(f"处理信号时发生错误: {str(e)}")
            return HttpResponse('处理信号时发生错误', status=500)

    return HttpResponse('不支持的请求方法', status=405)
