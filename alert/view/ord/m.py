"""
    行情API demo

    注意选择有效合约, 没有行情可能是过期合约或者不再交易时间内导致
"""
import inspect
import threading
import time
from openctp_ctp import mdapi

# #渠道名称
# channel_key = "simnow"
# #渠道环境名称
# environment_key = "电信1"
# channel_config = get_channel_config(channel_key, environment_key)


class CMdSpiImpl(mdapi.CThostFtdcMdSpi):
    def __init__(self, front: str,instruments:tuple):
        print("-------------------------------- 启动 mduser api demo ")
        super().__init__()
        self._front = front
        self.instruments = instruments
        print("接收到的行情合约:", self.instruments)

        self._api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(
            "market"
        )  # type: mdapi.CThostFtdcMdApi

        print("CTP行情API版本号:", self._api.GetApiVersion())
        print("行情前置:" + self._front)

        # 注册行情前置
        self._api.RegisterFront(self._front)
        # 注册行情回调实例
        self._api.RegisterSpi(self)
        # 初始化行情实例
        self._api.Init()
        print("初始化成功")

    def OnFrontConnected(self):
        """行情前置连接成功"""
        print("行情前置连接成功")

        # 登录请求, 行情登录不进行信息校验
        print("登录请求")
        req = mdapi.CThostFtdcReqUserLoginField()
        self._api.ReqUserLogin(req, 0)

    def OnRspUserLogin(
            self,
            pRspUserLogin: mdapi.CThostFtdcRspUserLoginField,
            pRspInfo: mdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """登录响应"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            print(f"登录失败: ErrorID={pRspInfo.ErrorID}, ErrorMsg={pRspInfo.ErrorMsg}")
            return

        print("登录成功")

        if len(self.instruments) == 0:
            return

        # 订阅行情
        print("订阅行情请求：", self.instruments)
        self._api.SubscribeMarketData(
            [i.encode("utf-8") for i in self.instruments], len(self.instruments)
        )

    def OnRtnDepthMarketData(
            self, pDepthMarketData: mdapi.CThostFtdcDepthMarketDataField
    ):
        """深度行情通知"""
        params = []
        for name, value in inspect.getmembers(pDepthMarketData):
            if name[0].isupper():
                params.append(f"{name}={value}")
        print("深度行情通知:", ",".join(params))

        # 提取 LowerLimitPrice 字段的值
        LowerLimitPrice_value = None
        for param in params:
            if "LowerLimitPrice" in param:
                LowerLimitPrice_value = param.split("=")[1]
                break
        #提取LastPrice 字段的值
        LastPrice_value = None
        for param in params:
            if "LastPrice" in param:
                LastPrice_value = param.split("=")[1]
                break

        # 打印 LowerLimitPrice 字段的值
        print("LowerLimitPrice 值:", LowerLimitPrice_value)
        print("LastPrice 值:", LastPrice_value)

    def OnRspSubMarketData(
            self,
            pSpecificInstrument: mdapi.CThostFtdcSpecificInstrumentField,
            pRspInfo: mdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """订阅行情响应"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            print(
                f"订阅行情失败:ErrorID={pRspInfo.ErrorID}, ErrorMsg={pRspInfo.ErrorMsg}",
            )
            return

        print("订阅行情成功:", pSpecificInstrument.InstrumentID)

    def wait(self):
        # 阻塞 等待
        input("-------------------------------- 按任意键退出 mduser api demo ")

        self._api.Release()


def query_price(channel_config, instruments):
    load_address=channel_config['md']
    spi = CMdSpiImpl(load_address,instruments)

    # 注意选择有效合约, 没有行情可能是过期合约或者不再交易时间内导致
    spi._api.SubscribeMarketData(
        [i.encode("utf-8") for i in instruments], len(instruments)
    )
    
    #创建一个线程来调用wait方法
    def wait_for_data():
        spi.wait()

    #启动线程
    wait_thread = threading.Thread(target=wait_for_data)
    wait_thread.start()

    #主线程保持活跃
    try:
        print("行情查询中，这个时候别乱跳出来了吧")
        while wait_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("程序被手动终止")
        spi._api.Release()
        wait_thread.join()


# if __name__ == "__main__":
#     load_address=channel_config['md']
#     spi = CMdSpiImpl(load_address)

#     # 注意选择有效合约, 没有行情可能是过期合约或者不再交易时间内导致
#     instruments = ("ru2501",
#                    "al2501",
#                    )
#     spi.wait()
