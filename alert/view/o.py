from config import channel_config
from api_m import query_price
from api_t import order_limit
from order_param import instruments,instrument_id

if __name__ == '__main__':
    #查询行情和价格
    # query_price(channel_config, instruments)
    #下单有限条件单
    order_limit(channel_config, instrument_id,19220,2,"buy","close")

    
