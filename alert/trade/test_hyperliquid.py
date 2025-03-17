import os
import sys
import django
import logging
from decimal import Decimal
from datetime import datetime
import time
import json
from django.db import transaction

# 设置Django环境
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'order7.settings')
django.setup()

from django.conf import settings
from alert.trade.hyperliquid_api import HyperliquidTrader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# 禁用不必要的日志
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("hyperliquid").setLevel(logging.WARNING)
logging.getLogger("alert.trade.hyperliquid_api").setLevel(logging.WARNING)  # 禁用API初始化信息

logger = logging.getLogger(__name__)

def test_query_order_details():
    """
    测试查询订单详情功能
    查询指定订单ID的详细信息，包括渠道订单ID、手续费和成交时间
    """
    try:
        logger.info("\n开始测试查询订单详情功能")
        
        # 初始化交易接口
        trader = HyperliquidTrader()
        
        # 输入要查询的订单ID
        order_id = input("请输入要查询的订单ID: ")
        
        # 从数据库中获取订单记录
        from alert.models import OrderRecord
        try:
            order_record = OrderRecord.objects.get(order_id=order_id)
            logger.info(f"找到订单记录: ID={order_record.id}, 交易对={order_record.symbol}, 状态={order_record.status}")
        except OrderRecord.DoesNotExist:
            logger.error(f"未找到订单ID为 {order_id} 的记录")
            return
        except OrderRecord.MultipleObjectsReturned:
            logger.warning(f"找到多个订单ID为 {order_id} 的记录，使用第一个")
            order_record = OrderRecord.objects.filter(order_id=order_id).first()
        
        # 使用get_order_details函数查询订单详情
        from alert.core.async_order_record import get_order_details
        logger.info(f"开始查询订单详情...")
        
        # 调用get_order_details函数，传递订单状态
        order_details = get_order_details(trader, order_record.symbol, order_id, order_record.status)
        logger.info(f"订单详情查询结果: {order_details}")
        
        # 如果订单状态为已成交，尝试更新数据库记录
        if order_record.status == "filled":
            logger.info("尝试更新数据库记录...")
            try:
                with transaction.atomic():
                    # 更新渠道订单ID
                    if "oid" in order_details and order_details["oid"] is not None:
                        order_record.oid = str(order_details["oid"])
                        logger.info(f"更新渠道订单ID: {order_record.oid}")
                    
                    # 更新手续费
                    if "fee" in order_details and order_details["fee"] is not None:
                        from decimal import Decimal
                        if not isinstance(order_details["fee"], Decimal):
                            order_record.fee = Decimal(str(order_details["fee"]))
                        else:
                            order_record.fee = order_details["fee"]
                        logger.info(f"更新手续费: {order_record.fee}")
                    
                    # 更新成交时间
                    if "filled_time" in order_details and order_details["filled_time"] is not None:
                        filled_time = order_details["filled_time"]
                        if isinstance(filled_time, datetime):
                            order_record.filled_time = filled_time
                        elif isinstance(filled_time, (int, float)):
                            # 将时间戳转换为datetime
                            if filled_time > 10000000000:  # 毫秒时间戳
                                seconds = filled_time / 1000
                            else:
                                seconds = filled_time
                            order_record.filled_time = datetime.fromtimestamp(seconds)
                        logger.info(f"更新成交时间: {order_record.filled_time}")
                    
                    # 保存更新
                    order_record.save()
                    logger.info("数据库记录更新成功")
                    
                    # 验证更新是否成功
                    updated_record = OrderRecord.objects.get(id=order_record.id)
                    logger.info(f"验证更新后的记录: oid={updated_record.oid}, fee={updated_record.fee}, filled_time={updated_record.filled_time}")
            except Exception as e:
                logger.error(f"更新数据库记录时出错: {str(e)}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
        
    except Exception as e:
        logger.error(f"测试查询订单详情时出错: {str(e)}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")

if __name__ == "__main__":
    # 运行订单详情查询测试
    test_query_order_details()