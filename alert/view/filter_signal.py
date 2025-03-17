from django.views.decorators.csrf import csrf_exempt
from alert.models import stra_Alert
from rest_framework.response import Response
from rest_framework import status
import logging
from alert.core.ordertask import order_monitor

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
        logger.warning(f"信号无效: {scode} {action} 与上一个信号方向相同")
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'Invalid trade signal, 当前信号无效, 请忽略'})

    # 如果没有找到之前一个信号，或者两个信号的action不同，将当前信号标记为有效
    logger.info(f"信号有效: {scode} {action}")
    # 移除保存操作，只返回结果
    return Response(status=status.HTTP_200_OK, data={'message': 'Valid trade signal, 当前信号有效, 请处理'})
