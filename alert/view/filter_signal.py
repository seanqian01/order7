from django.views.decorators.csrf import csrf_exempt
from alert.models import Strategy
from rest_framework.response import Response
from rest_framework import status
import logging
from alert.core.ordertask import order_monitor
from alert.strategy import RunStrategy


logger = logging.getLogger(__name__)

def filter_trade_signal(alert_data):
    strategy = alert_data.strategy
    
    # 检查策略ID是否提供
    if not strategy:
        logger.warning("策略ID未提供，当前信号无效")
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': '策略ID未提供，当前信号无效，请忽略'})
    
    # 验证策略的status是否有效
    try:
        if strategy.status == False:
            logger.warning(f"策略无效: {strategy.id} 策略已禁用, 请忽略")
            return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'Invalid trade signal, 当前策略已禁用, 请忽略'})
    except Exception as e:
        # 处理其他可能的异常
        logger.error(f"验证策略时出错: {str(e)}")
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={'message': f'Error during strategy validation: {str(e)}'})
    
    # 执行策略并获取结果
    strategy_result = RunStrategy(strategy.id, alert_data)
    
    # 根据策略结果返回相应的响应
    if strategy_result:
        return Response(status=status.HTTP_200_OK, data={'message': 'Valid trade signal, 当前信号有效, 请处理'})
    else:
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'message': 'Invalid trade signal, 当前信号无效, 请忽略'})
