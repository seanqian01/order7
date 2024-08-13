from ord.config import get_channel_config
from ord.m import query_price

#渠道名称
channel_key = "simnow"
#渠道环境名称
environment_key = "7x24"
channel_config = get_channel_config(channel_key, environment_key)

instruments=(
    "ru2501",
    "al2501",
    "ag2501",
)

if __name__ == '__main__':
    query_price(channel_config, instruments)
    
