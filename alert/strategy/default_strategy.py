from django.views.decorators.csrf import csrf_exempt
from alert.models import stra_Alert
from rest_framework.response import Response
from rest_framework import status
import logging
from alert.core.ordertask import order_monitor
from alert.strategy import register_strategy

logger = logging.getLogger(__name__)

@register_strategy(strategy_id=1)
def default_strategy(strategy_id, alert_data):
    """
    默认策略 (ID=1)
    检查信号是否有效，避免重复处理相同方向的信号
    
    :param strategy_id: 策略ID
    :param alert_data: 信号数据
    :return: True表示信号有效，False表示信号无效
    """
    try:
        # 获取信号基本信息
        scode = alert_data.scode
        time_circle = alert_data.time_circle
        action = alert_data.action
        
        # 查询数据库中相同scode的之前一个信号，按照created_at倒序排列
        previous_signal = stra_Alert.objects.filter(
            scode=scode, 
            time_circle=time_circle,
            created_at__lt=alert_data.created_at
        ).order_by('-created_at').first()

        # 如果找到之前一个信号，比较它们的action
        if previous_signal and previous_signal.action == action:
            # 如果两个信号的action相同，则将当前信号标记为无效
            logger.warning(f"检测到重复信号: {scode} {action} {time_circle}, 之前信号创建于 {previous_signal.created_at}")
            return False

        # 如果没有找到之前一个信号，或者两个信号的action不同，将当前信号标记为有效
        logger.info(f"信号有效: {scode} {action} {time_circle}")
        return True
        
    except Exception as e:
        logger.error(f"执行默认策略时出错: {str(e)}")
        return False