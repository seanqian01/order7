"""
    手动下载配置时的交易测试文件
    注意选择有效合约, 没有行情可能是过期合约或者不再交易时间内导致
"""

import inspect
import os
import sys

import thostmduserapi as mdapi

# 前置地址 参考 http://121.37.80.177:50080/detail.html  SimNow
FrontAddr = ""
# 注意选择有效合约, 没有行情可能是过期合约或者不在交易时间内的原因
# instruments = ["AP410"]


class CMdSpiImpl(mdapi.CThostFtdcMdSpi):
    def __init__(self):
        super().__init__()

        flow_path = os.path.join(os.getcwd(), "flow_logs", 'market')
        if not os.path.exists(flow_path):
            os.makedirs(flow_path)
        flow_path = os.path.join(flow_path, 'market')

        self._api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(flow_path)

        # 注册行情前置
        self._api.RegisterFront(FrontAddr)
        # 注册行情回调实例
        self._api.RegisterSpi(self)
        # 初始化行情实例
        self._api.Init()

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
            print(
                f"登录失败: ErrorID={pRspInfo.ErrorID}, ErrorMsg={pRspInfo.ErrorMsg}"
            )
            return

        print("登录成功")

        if len(instruments) == 0:
            return

        # 订阅行情
        print("订阅行情请求：", instruments)
        self._api.SubscribeMarketData(
            [i.encode("utf-8") for i in instruments], len(instruments)
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

    def OnRspSubMarketData(
            self,
            pSpecificInstrument: mdapi.CThostFtdcSpecificInstrumentField,
            pRspInfo: mdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """订阅行情响应"""
        if pRspInfo:
            print("订阅行情", pRspInfo.ErrorID, pRspInfo.ErrorMsg)
            return


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:    python demo_td <frontaddr> <instrument_id1> <instrument_id2> ...")
        exit(-1)

    FrontAddr = sys.argv[1]
    # 注意选择有效合约, 没有行情可能是过期合约或者不在交易时间内的原因
    instruments = sys.argv[2:]
    spi = CMdSpiImpl()
    input("############# 按任意键退出 \n")