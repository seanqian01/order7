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
            # 确保价格保由5位小数精度
            try:
                alert_price = float(alert_price)
                alert_price = round(alert_price, 5)
            except (ValueError, TypeError):
                pass
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
                # status默认为False，表示无效
            )
            
            # 检查信号是否有效（避免重复处理相同方向的信号）
            from alert.view.filter_signal import filter_trade_signal
            response = filter_trade_signal(trading_view_alert_data)
            
            if response.status_code == status.HTTP_200_OK:
                # 信号有效，设置状态为True
                trading_view_alert_data.status = True
                logger.info(f"信号有效，状态设置为True: {alert_symbol} {alert_action}")
                
                # 异步保存有效信号
                async_db_handler.async_save(trading_view_alert_data)
                logger.info(f"异步保存有效信号: {alert_symbol} {alert_action}")
                
                # 异步处理有效信号（添加到处理队列）
                # 注意：这里我们直接将信号添加到处理队列，因为信号处理器会在单独的线程中处理
                signal_processor.add_signal(trading_view_alert_data)
                logger.info(f"信号已添加到处理队列: {alert_symbol} {alert_action}")
                
                return HttpResponse('信号已接收并加入处理队列', status=200)
            else:
                # 信号无效，状态保持默认的False
                logger.warning(f"信号无效，状态保持为False: {alert_symbol} {alert_action}, 原因: {response.data.get('message', '未知原因')}")
                
                # 异步保存无效信号
                async_db_handler.async_save(trading_view_alert_data)
                logger.info(f"异步保存无效信号: {alert_symbol} {alert_action}")
                
                return HttpResponse(f"信号已接收但未加入处理队列: {response.data.get('message', '未知原因')}", status=200)

        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            return HttpResponse('无效的JSON数据', status=400)
        except Exception as e:
            logger.error(f"处理信号时发生错误: {str(e)}")
            return HttpResponse('处理信号时发生错误', status=500)

    return HttpResponse('不支持的请求方法', status=405)
