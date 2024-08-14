import time
from datetime import datetime, time as dt_time

#是否交易时间段
def is_trading_time():
    """
    检查当前时间是否在交易时间段内。

    :return: bool, 是否在交易时间内
    """
    current_time = datetime.now().time()

    # 夜盘时间段：21:00 - 23:59
    if dt_time(21, 0) <= current_time <= dt_time(23, 59):
        return True

    # 日盘时间段：09:00 - 15:00
    if dt_time(9, 0) <= current_time <= dt_time(15, 0):
        return True

    return False