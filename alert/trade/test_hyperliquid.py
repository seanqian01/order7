import os
import sys
import django
import logging
from decimal import Decimal
from datetime import datetime
import time
import json

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

# 禁用HTTP请求日志
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("hyperliquid").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def test_hyperliquid():
    """测试Hyperliquid永续合约接口"""
    trader = None
    try:
        start_time = time.time()
        logger.info(f"开始Hyperliquid接口测试 - {datetime.now()}")
        
        # 初始化交易接口
        env = settings.HYPERLIQUID_CONFIG["env"]
        logger.info(f"当前环境: {env}")
        
        trader = HyperliquidTrader()
        
        # 获取可用的交易对列表
        symbols = trader.get_default_symbols()
        logger.info(f"\n可用交易对列表: {', '.join(symbols)}")
        
        # 1. 测试账户信息
        logger.info("\n1. 账户信息")
        account_info = trader.get_account_info()
        
        if account_info["status"] == "success":
            margin = account_info.get("margin_summary", {})
            logger.info(f"账户总值: {margin.get('accountValue', '0')} USDC")
            logger.info(f"总持仓价值: {margin.get('totalNtlPos', '0')} USDC")
            logger.info(f"已用保证金: {margin.get('totalMarginUsed', '0')} USDC")
            logger.info(f"可提现金额: {account_info.get('withdrawable', '0')} USDC")
        else:
            logger.error(f"获取账户信息失败: {account_info.get('error')}")

        # 2. 测试永续合约持仓
        logger.info("\n2. 永续合约持仓")
        positions = trader.get_positions()  # 使用数据库中的活跃交易对
        
        if positions["status"] == "success":
            if positions["positions"]:
                for symbol, pos in positions["positions"].items():
                    logger.info(f"\n{pos['description']}:")
                    logger.info(f"  合约: {pos['symbol']} USDC永续")
                    logger.info(f"  持仓量: {pos['size']} 张")
                    logger.info(f"  开仓均价: {pos['entry_price']} USDC")
                    logger.info(f"  杠杆倍数: {pos['leverage']}x")
                    logger.info(f"  清算价格: {pos['liquidation_price']} USDC")
                    logger.info(f"  未实现盈亏: {pos['unrealized_pnl']} USDC")
                    logger.info(f"  已用保证金: {pos['margin_used']} USDC")
                    logger.info(f"  资金费率累计:")
                    logger.info(f"    全部: {pos['cum_funding']['all_time']}")
                    logger.info(f"    开仓后: {pos['cum_funding']['since_open']}")
                    logger.info(f"    变动后: {pos['cum_funding']['since_change']}")
            else:
                logger.info("当前无持仓")
        else:
            logger.error(f"获取持仓信息失败: {positions.get('error')}")

        # 3. 测试订单查询
        logger.info("\n3. 订单查询")
        # 查询当天订单
        orders = trader.get_orders("S")
        
        if orders["status"] == "success":
            if orders["orders"]:
                logger.info(f"今日订单记录 ({len(orders['orders'])}条):")
                for order in orders["orders"]:
                    logger.info(f"\n  订单号: {order['order_id']}")
                    logger.info(f"  时间: {order['time']}")
                    logger.info(f"  合约: {order['symbol']} USDC永续")
                    logger.info(f"  类型: {order['type']}")
                    logger.info(f"  方向: {order['side']}")
                    logger.info(f"  价格: {order['price']} USDC")
                    logger.info(f"  数量: {order['size']} 张")
                    logger.info(f"  状态: {order['status']}")
                    if order['status'] == 'FILLED':
                        logger.info(f"  成交量: {order['filled_size']} 张")
                        logger.info(f"  手续费: {order['fee']} USDC")
            else:
                logger.info("今日无订单记录")
        else:
            logger.error(f"获取订单记录失败: {orders.get('error')}")

        logger.info(f"\n测试完成! 总耗时: {(time.time() - start_time):.2f}秒")

    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}")
        raise e
    finally:
        # 确保关闭所有连接
        if trader:
            if hasattr(trader.info, 'close'):
                trader.info.close()
            if hasattr(trader.exchange, 'close'):
                trader.exchange.close()
        # 退出所有线程
        import sys
        sys.exit(0)

def test_trading_signal():
    """测试交易信号处理功能"""
    from django.utils import timezone
    from alert.models import stra_Alert, TimeCycle
    from alert.view.signal import place_hyperliquid_order
    
    # 创建测试用的时间周期
    time_circle, _ = TimeCycle.objects.get_or_create(name="5m")
    
    # 创建一个模拟的交易信号
    test_signal = stra_Alert(
        alert_title="Test Signal",
        symbol="HYPE-USDC",
        scode="HYPE",
        contractType=3,  # 虚拟货币
        price="10.5",    # 使用当前市场价格附近的价格
        action="buy",
        created_at=timezone.now(),
        time_circle=time_circle
    )
    test_signal.save()
    
    # 测试交易执行
    print("\n开始测试交易信号处理...")
    success = place_hyperliquid_order(test_signal)
    
    if success:
        print("✅ 交易信号处理成功")
    else:
        print("❌ 交易信号处理失败")
    
    # 清理测试数据
    test_signal.delete()

if __name__ == "__main__":
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'order7.settings')
    django.setup()
    
    # 运行所有测试
    print("\n=== 开始测试 Hyperliquid API ===")
    test_hyperliquid()
    test_trading_signal()
    print("\n=== 测试完成 ===")