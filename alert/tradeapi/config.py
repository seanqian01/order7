"""
    配置了 SimNow 常用的四个环境
    可以使用监控平台 http://121.37.80.177:50080/detail.html 查看前置服务是否正常
"""

# 也可以按需配置其他的支持 ctp官方ctpapi库的柜台
# 注意需要同时修改相应的 user/password/broker_id/authcode/appid 等信息

# SimNow 提供的四个环境
fronts = {
    "7x24": {
        "td": "tcp://180.168.146.187:10130",
        "md": "tcp://180.168.146.187:10131",
    },
    "电信1": {
        "td": "tcp://180.168.146.187:10201",
        "md": "tcp://180.168.146.187:10211",
    },
    "电信2": {
        "td": "tcp://180.168.146.187:10202",
        "md": "tcp://180.168.146.187:10212",
    },
    "移动": {
        "td": "tcp://218.202.237.33:10203",
        "md": "tcp://218.202.237.33:10213",
    },
    "通惠测试": {
        "td": "tcp://210.22.130.34:41505",
        "md": "tcp://210.22.130.34:41513",
    },
}

# simnow投资者ID / 密码
user = "221882"
password = "mikalqlr009!"

# 以下为连接 SimNow 环境的固定值
broker_id = "9999"
authcode = "0000000000000000"
appid = "simnow_client_test"

# # 通惠测试环境投资者ID / 密码
# user = "08860"
# password = "thqh1234"
#
# # 以下为通惠测试环境的固定值
# broker_id = "08860"
# authcode = "P2UAXBUJ3VPVMUBY"
# appid = "client_vcpos_2.0"
