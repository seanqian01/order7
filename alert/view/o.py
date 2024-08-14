from config import channel_config, instruments,instrument_id
from m import query_price
from t import order_limit


if __name__ == '__main__':
    #查询行情和价格
    query_price(channel_config, instruments)
    #下单有限条件单
    order_limit(channel_config, instrument_id,19250,1,"sell","open")

    
