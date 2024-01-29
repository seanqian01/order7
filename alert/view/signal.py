from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from alert.models import stra_Alert
import json
from rest_framework.response import Response
from rest_framework import status


def filter_trade_signal(alert_data):
    # 获取当前信号的scode和action
    scode = alert_data.scode
    action = alert_data.action

    # 查询数据库中相同scode的之前一个信号，按照created_at倒序排列
    previous_signal = stra_Alert.objects.filter(scode=scode, created_at__lt=alert_data.created_at).order_by(
        '-created_at').first()

    # 如果找到之前一个信号，比较它们的action
    if previous_signal and previous_signal.action == action:
        # 如果两个信号的action相同，则将当前信号标记为无效
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'Invalid trade signal, 当前信号无效, 请忽略'})

    # 如果没有找到之前一个信号，或者两个信号的action不同，将当前信号标记为有效
    alert_data.status = True
    alert_data.save()

    return Response(status=status.HTTP_200_OK, data={'message': 'Valid trade signal, 当前信号有效, 请处理'})


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
                # alert_amount = json_data.get('amount')

                # alert_message = json_data['message']
                # beijing_tz = timezone(timedelta(hours=8), 'Asia/Shanghai')
                # utc_time = datetime.utcnow()
                trading_view_alert_data = stra_Alert(
                    alert_title=alert_title1,
                    symbol=alert_symbol,
                    scode=alert_scode,
                    contractType=alert_contractType,
                    price=alert_price,
                    action=alert_action,
                    # amount=alert_amount,
                    created_at=timezone.now(),
                )
                trading_view_alert_data.save()

                # 调用过滤函数
                # filter_trade_signal(trading_view_alert_data)
                with transaction.atomic():
                    # 在事务中处理信号
                    response = filter_trade_signal(trading_view_alert_data)
                # return HttpResponse('成功接收数据且存储完成', status=200)
                return HttpResponse(response.data['message'], status=response.status_code)

            else:
                return HttpResponse('信号无效请重试', status=300)
    return HttpResponse('没有数据接收到', status=400)
