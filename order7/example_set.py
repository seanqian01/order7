
# 数据库配置
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
        'OPTIONS': {'charset': 'utf8mb4'},
        
    }
}


# Hyperliquid配置
HYPERLIQUID_CONFIG = {
# 主网配置
    "mainnet": {
        "wallet_address": "",# 主网钱包地址
        "api_secret": "",# 主网API密钥
        "api_url": "https://api.hyperliquid.xyz",
    },
# 测试网配置
    "testnet": {
        "wallet_address": "",# 测试网钱包地址
        "api_secret": "",# 测试网API密钥
        "api_url": "https://api.hyperliquid-testnet.xyz",
    },
# 通用配置
    "env": "",# 环境选择：'mainnet' 或 'testnet'
    "default_leverage": 3,# 默认杠杆

}
