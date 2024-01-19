

# Create your views here.
import json

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .models import stra_Alert


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
                # 调用处理函数
                # process_data(trading_view_alert_data)
                return HttpResponse('成功接收数据且存储完成', status=200)
            else:
                return HttpResponse('信号无效请重试', status=300)
    return HttpResponse('没有数据接收到', status=400)
