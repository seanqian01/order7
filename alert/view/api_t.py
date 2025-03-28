"""
    交易API demo
"""
import inspect
import queue
import time
import sys

from openctp_ctp import tdapi
from trading_time import is_trading_time
from config import channel_config
from order_param import exchange_id

sys.path.append("..")

# channel_key = "simnow"
# environment_key = "电信1"
# channel_config = get_channel_config(channel_key, environment_key)


class CTdSpiImpl(tdapi.CThostFtdcTraderSpi):
    """交易回调实现类"""

    def __init__(
            self,
            front: str,
            user: str,
            passwd: str,
            authcode: str,
            appid: str,
            broker_id: str,
    ):
        print("-------------------------------- 启动 trader api demo ")
        super().__init__()
        self._front = front
        self._user = user
        self._password = passwd
        self._authcode = authcode
        self._appid = appid
        self._broker_id = broker_id

        self._is_authenticate = False
        self._is_login = False

        self._is_last = True
        self._print_max = 2
        self._print_count = 0
        self._total = 0

        self._wait_queue = queue.Queue(1)

        self._api: tdapi.CThostFtdcTraderApi = (
            tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi(self._user)
        )

        print("CTP交易API版本号:", self._api.GetApiVersion())
        print("交易前置:" + self._front)

        # 注册交易前置
        self._api.RegisterFront(self._front)
        # 注册交易回调实例
        self._api.RegisterSpi(self)
        # 订阅私有流
        self._api.SubscribePrivateTopic(tdapi.THOST_TERT_QUICK)
        # 订阅公有流
        self._api.SubscribePublicTopic(tdapi.THOST_TERT_QUICK)
        # 初始化交易实例
        self._api.Init()
        print("初始化成功")

    @property
    def is_login(self):
        return self._is_login

    def release(self):
        # 释放实例
        self._api.Release()

    def _check_req(self, req, ret: int):
        """检查请求"""

        # 打印请求
        params = []
        for name, value in inspect.getmembers(req):
            if name[0].isupper():
                params.append(f"{name}={value}")
        self.print("发送请求:", ",".join(params))

        # 检查请求结果
        error = {
            0: "",
            -1: "网络连接失败",
            -2: "未处理请求超过许可数",
            -3: "每秒发送请求数超过许可数",
        }.get(ret, "未知错误")
        if ret != 0:
            self.print(f"请求失败: {ret}={error}")

    def _check_rsp(
            self, pRspInfo: tdapi.CThostFtdcRspInfoField, rsp=None, is_last: bool = True
    ) -> bool:
        """检查响应

        True: 成功 False: 失败
        """

        if self._is_last:
            if pRspInfo and pRspInfo.ErrorID != 0:
                self.print(
                    f"响应失败, ErrorID={pRspInfo.ErrorID}, ErrorMsg={pRspInfo.ErrorMsg}"
                )
                return False

            self.print("响应成功")
            if rsp:
                params = []
                for name, value in inspect.getmembers(rsp):
                    if name[0].isupper():
                        params.append(f"{name}={value}")
                self.print("响应内容:", ",".join(params))
            else:
                self.print("响应为空")

            if not is_last:
                self._print_count += 1
                self._total = +1
            else:
                if self._is_login:
                    self._wait_queue.put_nowait(None)

        else:
            if self._print_count < self._print_max:
                if rsp:
                    params = []
                    for name, value in inspect.getmembers(rsp):
                        if name[0].isupper():
                            params.append(f"{name}={value}")
                    self.print("     ", ",".join(params))

                self._print_count += 1

            self._total += 1

            if is_last:
                self.print("总计数量:", self._total, "打印数量:", self._print_count)

                self._print_count = 0
                self._total = 0

                if self._is_login:
                    self._wait_queue.put_nowait(None)

        self._is_last = is_last

        return True

    @staticmethod
    def print_rsp_rtn(prefix, rsp_rtn):
        if rsp_rtn:
            params = []
            for name, value in inspect.getmembers(rsp_rtn):
                if name[0].isupper():
                    params.append(f"{name}={value}")
            print(">", prefix, ",".join(params))

    @staticmethod
    def print(*args, **kwargs):
        print("    ", *args, **kwargs)

    def OnFrontConnected(self):
        """交易前置连接成功"""
        print("交易前置连接成功")

        self.authenticate()

    def OnFrontDisconnected(self, nReason: int):
        """交易前置连接断开"""
        print("交易前置连接断开: nReason=", nReason)

        # todo 可以在这里定义交易连接断开时的逻辑

    def authenticate(self):
        """认证 demo"""
        print("> 认证")
        _req = tdapi.CThostFtdcReqAuthenticateField()
        _req.BrokerID = self._broker_id
        _req.UserID = self._user
        _req.AppID = self._appid
        _req.AuthCode = self._authcode
        self._check_req(_req, self._api.ReqAuthenticate(_req, 0))

    def OnRspAuthenticate(
            self,
            pRspAuthenticateField: tdapi.CThostFtdcRspAuthenticateField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """客户端认证响应"""
        if not self._check_rsp(pRspInfo, pRspAuthenticateField):
            return

        self._is_authenticate = True

        # 登录
        self.login()

    def login(self):
        """登录 demo"""
        print("> 登录")

        _req = tdapi.CThostFtdcReqUserLoginField()
        _req.BrokerID = self._broker_id
        _req.UserID = self._user
        _req.Password = self._password
        if sys.platform == "darwin":
            self._check_req(_req, self._api.ReqUserLogin(_req, 0, 0, ""))
        else:
            self._check_req(_req, self._api.ReqUserLogin(_req, 0))

    def OnRspUserLogin(
            self,
            pRspUserLogin: tdapi.CThostFtdcRspUserLoginField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """登录响应"""
        if not self._check_rsp(pRspInfo, pRspUserLogin):
            return

        self._is_login = True

    def settlement_info_confirm(self):
        """投资者结算结果确认"""
        print("> 投资者结算结果确认")

        _req = tdapi.CThostFtdcSettlementInfoConfirmField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        self._check_req(_req, self._api.ReqSettlementInfoConfirm(_req, 0))

    def OnRspSettlementInfoConfirm(
            self,
            pSettlementInfoConfirm: tdapi.CThostFtdcSettlementInfoConfirmField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """投资者结算结果确认响应"""
        if not self._check_rsp(pRspInfo, pSettlementInfoConfirm):
            return

    def qry_instrument(
            self, exchange_id: str = "", product_id: str = "", instrument_id: str = ""
    ):
        """请求查询合约"""
        print("> 请求查询合约")
        _req = tdapi.CThostFtdcQryInstrumentField()
        # 填空可以查询到所有合约
        # 也可分别根据交易所、品种、合约 三个字段查询指定的合约
        _req.ExchangeID = exchange_id
        _req.ProductID = product_id
        _req.InstrumentID = instrument_id
        self._check_req(_req, self._api.ReqQryInstrument(_req, 0))

    def OnRspQryInstrument(
            self,
            pInstrument: tdapi.CThostFtdcInstrumentField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """请求查询合约响应"""
        if not self._check_rsp(pRspInfo, pInstrument, bIsLast):
            return

    def qry_instrument_commission_rate(self, instrument_id: str = ""):
        """请求查询合约手续费率"""
        print("> 请求查询合约手续费率")
        _req = tdapi.CThostFtdcQryInstrumentCommissionRateField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        # 若不指定合约ID, 则返回当前持仓对应合约的手续费率
        _req.InstrumentID = instrument_id
        self._check_req(_req, self._api.ReqQryInstrumentCommissionRate(_req, 0))

    def OnRspQryInstrumentCommissionRate(
            self,
            pInstrumentCommissionRate: tdapi.CThostFtdcInstrumentCommissionRateField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """请求查询合约手续费率响应"""
        if not self._check_rsp(pRspInfo, pInstrumentCommissionRate, bIsLast):
            return

    def qry_instrument_margin_rate(self, instrument_id: str = ""):
        """请求查询合约保证金率"""
        print("> 请求查询合约保证金率")
        _req = tdapi.CThostFtdcQryInstrumentMarginRateField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        _req.HedgeFlag = tdapi.THOST_FTDC_HF_Speculation
        # 若不指定合约ID, 则返回当前持仓对应合约的保证金率
        _req.InstrumentID = instrument_id
        self._check_req(_req, self._api.ReqQryInstrumentMarginRate(_req, 0))

    def OnRspQryInstrumentMarginRate(
            self,
            pInstrumentMarginRate: tdapi.CThostFtdcInstrumentMarginRateField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """请求查询合约保证金率响应"""
        if not self._check_rsp(pRspInfo, pInstrumentMarginRate, bIsLast):
            return

    def qry_depth_market_data(self, instrument_id: str = ""):
        """请求查询行情，只能查询当前快照，不能查询历史行情"""
        print("> 请求查询行情")
        _req = tdapi.CThostFtdcQryDepthMarketDataField()
        # 若不指定合约ID, 则返回所有合约的行情
        _req.InstrumentID = instrument_id
        self._check_req(_req, self._api.ReqQryDepthMarketData(_req, 0))

    def OnRspQryDepthMarketData(
            self,
            pDepthMarketData: tdapi.CThostFtdcDepthMarketDataField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """请求查询行情响应"""
        if not self._check_rsp(pRspInfo, pDepthMarketData, bIsLast):
            return

    def market_order_insert(
            self, exchange_id: str, instrument_id: str, volume: int = 1
    ):
        """报单录入请求(市价单)

        - 录入错误时对应响应OnRspOrderInsert、OnErrRtnOrderInsert，
        - 正确时对应回报OnRtnOrder、OnRtnTrade。
        """
        print("> 报单录入请求(市价单)")

        # 市价单, 注意选择一个相对活跃的合约
        # simnow 目前貌似不支持市价单，所以会被自动撤销！！！
        _req = tdapi.CThostFtdcInputOrderField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        _req.ExchangeID = exchange_id
        _req.InstrumentID = instrument_id
        _req.LimitPrice = 0
        _req.OrderPriceType = tdapi.THOST_FTDC_OPT_AnyPrice  # 价格类型市价单
        _req.Direction = tdapi.THOST_FTDC_D_Buy  # 买
        _req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open  # 开仓
        _req.CombHedgeFlag = tdapi.THOST_FTDC_HF_Speculation
        _req.VolumeTotalOriginal = volume
        _req.IsAutoSuspend = 0
        _req.IsSwapOrder = 0
        _req.TimeCondition = tdapi.THOST_FTDC_TC_GFD
        _req.VolumeCondition = tdapi.THOST_FTDC_VC_AV
        _req.ContingentCondition = tdapi.THOST_FTDC_CC_Immediately
        _req.ForceCloseReason = tdapi.THOST_FTDC_FCC_NotForceClose
        self._check_req(_req, self._api.ReqOrderInsert(_req, 0))

    def limit_order_insert(
            self,
            exchange_id: str,
            instrument_id: str,
            price: float,
            volume: int = 1,
            direction: str='buy',
            offset_flag: str='open',
            close_today:bool =False,
    ):
        """报单录入请求(限价单)

        - 录入错误时对应响应OnRspOrderInsert、OnErrRtnOrderInsert，
        - 正确时对应回报OnRtnOrder、OnRtnTrade。
        """
        print("> 报单录入请求(限价单)")

        # 限价单 注意选择一个相对活跃的合约及合适的价格
        _req = tdapi.CThostFtdcInputOrderField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        _req.ExchangeID = exchange_id
        _req.InstrumentID = instrument_id  # 合约ID
        _req.LimitPrice = price  # 价格
        _req.OrderPriceType = tdapi.THOST_FTDC_OPT_LimitPrice  # 价格类型限价单

        # 定义买卖方向
        if direction.lower() == 'buy':
            _req.Direction = tdapi.THOST_FTDC_D_Buy  # 买
        elif direction.lower() == 'sell':
            _req.Direction = tdapi.THOST_FTDC_D_Sell  # 卖
        else:
            raise ValueError("Invalid direction value, must be 'buy' or 'sell'")

        # 定义开仓和平仓
        if offset_flag.lower() == 'open':
            _req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open  # 开仓
        elif offset_flag.lower() == 'close':
            if close_today:
                _req.CombOffsetFlag = tdapi.THOST_FTDC_OF_CloseToday  # 平今
            else:
                _req.CombOffsetFlag = tdapi.THOST_FTDC_OF_CloseYesterday  # 平昨
        else:
            raise ValueError("Invalid offset_flag value, must be 'open' or 'close'")

        # _req.Direction = tdapi.THOST_FTDC_D_Buy  # 买
        # _req.CombOffsetFlag = tdapi.THOST_FTDC_OF_Open  # 开仓
        _req.CombHedgeFlag = tdapi.THOST_FTDC_HF_Speculation
        _req.VolumeTotalOriginal = volume
        _req.IsAutoSuspend = 0
        _req.IsSwapOrder = 0
        _req.TimeCondition = tdapi.THOST_FTDC_TC_GFD
        _req.VolumeCondition = tdapi.THOST_FTDC_VC_AV
        _req.ContingentCondition = tdapi.THOST_FTDC_CC_Immediately
        _req.ForceCloseReason = tdapi.THOST_FTDC_FCC_NotForceClose
        self._check_req(_req, self._api.ReqOrderInsert(_req, 0))

    def OnRspOrderInsert(
            self,
            pInputOrder: tdapi.CThostFtdcInputOrderField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """报单录入请求响应"""
        self._check_rsp(pRspInfo, pInputOrder, bIsLast)

    def order_cancel1(
            self, exchange_id: str, instrument_id: str, order_sys_id: str
    ):
        """报单撤销请求 方式一

        - 错误响应: OnRspOrderAction，OnErrRtnOrderAction
        - 正确响应：OnRtnOrder
        """
        print("> 报单撤销请求 方式一")

        # 撤单请求，首先需要有一笔未成交的订单，可以使用限价单，按照未成交订单信息填写撤单请求
        _req = tdapi.CThostFtdcInputOrderActionField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        _req.UserID = self._user
        _req.ExchangeID = exchange_id
        _req.InstrumentID = instrument_id
        _req.ActionFlag = tdapi.THOST_FTDC_AF_Delete

        _req.OrderSysID = order_sys_id  # OrderSysId 中空格也要带着

        # 若成功，会通过 报单回报 返回新的订单状态, 若失败则会响应失败
        self._check_req(_req, self._api.ReqOrderAction(_req, 0))

    def order_cancel2(
            self,
            exchange_id: str,
            instrument_id: str,
            front_id: int,
            session_id: int,
            order_ref: str,
    ):
        """报单撤销请求 方式二

        - 错误响应: OnRspOrderAction，OnErrRtnOrderAction
        - 正确响应：OnRtnOrder
        """
        print("> 报单撤销请求 方式二")

        # 撤单请求，首先需要有一笔未成交的订单，可以使用限价单，按照未成交订单信息填写撤单请求
        _req = tdapi.CThostFtdcInputOrderActionField()
        _req.BrokerID = self._broker_id
        _req.InvestorID = self._user
        _req.UserID = self._user
        _req.ExchangeID = exchange_id
        _req.InstrumentID = instrument_id
        _req.ActionFlag = tdapi.THOST_FTDC_AF_Delete

        _req.OrderRef = order_ref
        _req.FrontID = front_id
        _req.SessionID = session_id

        # 若成功，会通过 报单回报 返回新的订单状态, 若失败则会响应失败
        self._check_req(_req, self._api.ReqOrderAction(_req, 0))

    def OnRspOrderAction(
            self,
            pInputOrderAction: tdapi.CThostFtdcInputOrderActionField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """报单操作请求响应"""
        self._check_rsp(pRspInfo, pInputOrderAction, bIsLast)

    def OnRtnOrder(self, pOrder: tdapi.CThostFtdcOrderField):
        """报单通知，当执行ReqOrderInsert后并且报出后，收到返回则调用此接口，私有流回报。"""
        self.print_rsp_rtn("报单通知", pOrder)

    def OnRtnTrade(self, pTrade: tdapi.CThostFtdcTradeField):
        """成交通知，报单发出后有成交则通过此接口返回。私有流"""
        self.print_rsp_rtn("成交通知", pTrade)

    def OnErrRtnOrderInsert(
            self,
            pInputOrder: tdapi.CThostFtdcInputOrderField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
    ):
        """"""
        self._check_rsp(pRspInfo, pInputOrder)

    def qry_trading_code(self, exchange_id: str):
        """请求查询交易编码"""
        print("> 请求查询交易编码")
        req = tdapi.CThostFtdcQryTradingCodeField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user
        req.ExchangeID = exchange_id
        self._check_req(req, self._api.ReqQryTradingCode(req, 0))

    def OnRspQryTradingCode(
            self,
            pTradingCode: tdapi.CThostFtdcTradingCodeField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """请求查询交易编码响应"""
        self._check_rsp(pRspInfo, pTradingCode, bIsLast)

    def qry_exchange(self, exchange_id: str):
        """查询交易所"""
        print("> 查询交易所")
        req = tdapi.CThostFtdcQryExchangeField()
        req.ExchangeID = exchange_id
        self._check_req(req, self._api.ReqQryExchange(req, 0))

    def OnRspQryExchange(
            self,
            pExchange: tdapi.CThostFtdcExchangeField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """查询交易所应答"""
        self._check_rsp(pRspInfo, pExchange, bIsLast)

    def user_password_update(self, new_password: str, old_password: str):
        """用户口令变更"""
        print("> 用户口令变更请求")

        req = tdapi.CThostFtdcUserPasswordUpdateField()
        req.BrokerID = self._broker_id
        req.UserID = self._user
        req.OldPassword = old_password
        req.NewPassword = new_password

        self._check_req(req, self._api.ReqUserPasswordUpdate(req, 0))

    def OnRspUserPasswordUpdate(
            self,
            pUserPasswordUpdate: tdapi.CThostFtdcUserPasswordUpdateField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """用户口令变更响应"""
        self._check_rsp(pRspInfo, pUserPasswordUpdate, bIsLast)

    def qry_order_comm_rate(self, instrument_id: str):
        """查询申报费率"""
        print("> 请求查询申报费率")
        req = tdapi.CThostFtdcQryInstrumentOrderCommRateField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user
        req.InstrumentID = instrument_id
        self._check_req(req, self._api.ReqQryInstrumentOrderCommRate(req, 0))

    def OnRspQryInstrumentOrderCommRate(
            self,
            pInstrumentOrderCommRate: tdapi.CThostFtdcInstrumentOrderCommRateField,
            pRspInfo: tdapi.CThostFtdcRspInfoField,
            nRequestID: int,
            bIsLast: bool,
    ):
        """查询申报费率应答"""
        self._check_rsp(pRspInfo, pInstrumentOrderCommRate, bIsLast)

    def qry_investor_position(self, instrument_id: str = ""):
        """查询投资者持仓"""
        print("> 请求查询投资者持仓")
        req = tdapi.CThostFtdcQryInvestorPositionField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user
        req.InstrumentID = instrument_id  # 可指定合约
        self._check_req(req, self._api.ReqQryInvestorPosition(req, 0))

    def OnRspQryInvestorPosition(
        self,
        pInvestorPosition: tdapi.CThostFtdcInvestorPositionField,
        pRspInfo: tdapi.CThostFtdcRspInfoField,
        nRequestID: int,
        bIsLast: bool,
    ):
        """查询投资者持仓响应"""
        self._check_rsp(pRspInfo, pInvestorPosition, bIsLast)
        
        if pInvestorPosition:
            PosiDirction=pInvestorPosition.PosiDirection
            OpenVolume=pInvestorPosition.OpenVolume
            Position=pInvestorPosition.Position
            print(f"持仓方向：{PosiDirction}",
                f"持仓可交易开仓量：{OpenVolume}",
                f"持仓量：{Position}")

    def qry_investor_position_detail(self, instrument_id: str = ""):
        """查询投资者持仓"""
        print("> 请求查询投资者持仓明细")
        req = tdapi.CThostFtdcQryInvestorPositionDetailField()
        req.BrokerID = self._broker_id
        req.InvestorID = self._user
        req.InstrumentID = instrument_id  # 可指定合约
        self._check_req(req, self._api.ReqQryInvestorPositionDetail(req, 0))

    def OnRspQryInvestorPositionDetail(
        self,
        pInvestorPositionDetail: tdapi.CThostFtdcInvestorPositionDetailField,
        pRspInfo: tdapi.CThostFtdcRspInfoField,
        nRequestID: int,
        bIsLast: bool,
    ):
        """查询投资者持仓明细响应"""
        self._check_rsp(pRspInfo, pInvestorPositionDetail, bIsLast)

    def wait(self):
        # 阻塞 等待
        self._wait_queue.get()
        input("-------------------------------- 按任意键退出 trader api demo ")

        self.release()


if __name__ == "__main__":
    front=channel_config['td']
    spi = CTdSpiImpl(
        front,
        channel_config["user"],
        channel_config["password"],
        channel_config["authcode"],
        channel_config["appid"],
        channel_config["broker_id"],
    )

    # 等待登录成功
    try:
        while True:
            time.sleep(1)
            if spi.is_login:
                # SHFE:上期所 | DCE:大商所  |CZCE:郑商所 | CFFEX:中金所 | INE:能源中心

                # 投资者结算结果确认
                # spi.settlement_info_confirm()

                # 请求查询合约
                # spi.qry_instrument("DCE")
                # spi.qry_instrument(exchange_id="CZCE")
                # spi.qry_instrument(product_id="i")
                # spi.qry_instrument(instrument_id="RU2501")

                # 请求查询合约手续费
                # spi.qry_instrument_commission_rate("fu2409")

                # 请求查询合约保证金率
                # spi.qry_instrument_margin_rate(instrument_id="fu2409")
                # spi.qry_depth_market_data()

                # 请求查询行情
                # spi.qry_depth_market_data(instrument_id="al2410")

                # spi.market_order_insert("CZCE", "RM411",2)
                # spi.limit_order_insert("SHFE", "al2410", 19125, 1,'sell', 'close',True)
                # spi.limit_order_insert("CZCE", "RS407", 5670, 1)

                # 订单撤单需要带上原始订单号
                # spi.order_cancel1("CZCE", "RM411", "2024041100000006")
                # spi.order_cancel2("CZCE", "CF411", 1, -1111111, "3")

                # 请求查询交易编码
                # spi.qry_trading_code("CZCE")

                # 查询交易所
                # spi.qry_exchange("DCE")

                #查询交易者持仓
                spi.qry_investor_position("al2501")

                # 查询交易者持仓明细
                # spi.qry_investor_position_detail("jd2409")

                # spi.user_password_update("sWJedore20@#0808", "sWJedore20@#0807")
                # spi.qry_order_comm_rate("ss2407")
                break

        # 代码中的请求参数编写时测试通过, 不保证以后一定成功。
        # 需要测试哪个请求, 取消下面对应的注释, 并按需修改参请求参数即可。

        # spi.limit_order_insert("CZCE", "CF411", 12000, 1)

        # spi.settlement_info_confirm()
        # spi.qry_instrument()
        # spi.qry_instrument(exchange_id="CZCE","DCE")
        # spi.qry_instrument(product_id="AP")
        # spi.qry_instrument(instrument_id="fu2405")
        # spi.qry_instrument_commission_rate("br2409")
        # spi.qry_instrument_margin_rate()
        # spi.qry_instrument_margin_rate(instrument_id="ZC309")
        # spi.qry_depth_market_data()
        # spi.qry_depth_market_data(instrument_id="ZC309")
        # spi.market_order_insert("CZCE", "CF411")
        # spi.limit_order_insert("CZCE", "CF411", 15000)
        # spi.order_cancel1("CZCE", "CF411", "        4858")
        # spi.order_cancel2("CZCE", "CF411", 1, -1111111, "3")
        # spi.qry_trading_code("CZCE")
        # spi.qry_exchange("DCE")
        # spi.user_password_update("sWJedore20@#0808", "sWJedore20@#0807")
        # spi.qry_order_comm_rate("ss2407")
            if not spi.is_login:
                break
        spi.wait()
        # pass
    except KeyboardInterrupt:
        spi.close()
        print("检测到键盘终止信号, 退出程序")
    
    print("程序结束")

is_settlement_confirmed = None

def order_limit(channel_config, instrument_id, price, volume, direction, offset):
    """
    封装的有限单下单函数。

    :param channel_config: dict, 包含交易相关的配置参数
    :param instrument_id: str, 合约代码
    :param price: float, 下单价格
    :param volume: int, 下单数量
    :param direction: str, 交易方向 ('buy' 或 'sell')
    :param offset: str, 开平标志 ('open' 或 'close')
    """
    global is_settlement_confirmed

    # 初始化交易对象
    front = channel_config['td']
    spi = CTdSpiImpl(
        front,
        channel_config["user"],
        channel_config["password"],
        channel_config["authcode"],
        channel_config["appid"],
        channel_config["broker_id"],
    )

    # 等待登录成功
    try:
        while not spi.is_login:
            print("未登录，等待登录...")
            time.sleep(1)
        print("登录成功")
    except Exception as e:
        print(f"登录失败: {e}")
        spi.release()
        return

    # 在首次启动或交易时间段内进行结算确认
    if not is_settlement_confirmed and is_trading_time():
        try:
            print("进行结算确认")
            spi.settlement_info_confirm()
            is_settlement_confirmed = True
            print("结算确认成功")
        except Exception as e:
            print(f"结算确认失败: {e}")
            spi.release()
            return

    # 执行下单
    try:
        spi.limit_order_insert(
            exchange_id,
            instrument_id,  # 确保 instrument_id 不超过 81 个字符
            price,
            volume,
            direction,
            offset,
            False
        )
        print("下单成功")
        spi.wait()
    except Exception as e:
        print(f"下单失败: {e}")
    finally:
        spi.release()  # 确保在完成操作后释放资源
        print("连接释放")


