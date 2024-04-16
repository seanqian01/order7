import time

from tdapi import CTdSpiImpl
import config

if __name__ == "__main__":
    spi = CTdSpiImpl(
        config.fronts["电信2"]["td"],
        config.user,
        config.password,
        config.authcode,
        config.appid,
        config.broker_id,
    )

    # 等待登录成功
    while True:
        time.sleep(1)
        if spi.is_login:
            # 投资者结算结果确认
            # spi.settlement_info_confirm()

            # SHFE:上期所 | DCE:大商所  |CZCE:郑商所 | CFFEX:中金所 | INE:能源中心

            # 请求查询合约
            # spi.qry_instrument("CZCE")
            # spi.qry_instrument(exchange_id="CZCE")
            # spi.qry_instrument(product_id="i")
            # spi.qry_instrument(instrument_id="CF411")

            # 请求查询合约手续费
            # spi.qry_instrument_commission_rate("fu2409")

            # 请求查询合约保证金率
            # spi.qry_instrument_margin_rate(instrument_id="fu2409")
            # spi.qry_depth_market_data()

            # 请求查询行情
            # spi.qry_depth_market_data(instrument_id="CF411")

            # 市价单
            # spi.market_order_insert("CZCE", "RM411")

            # 限价单
            # spi.limit_order_insert("SHFE", "ag2409", 7459, 1)
            # spi.limit_order_insert("CZCE", "RS407", 5670, 1)

            # 订单撤单需要带上原始订单号
            # spi.order_cancel1("CZCE", "RM411", "2024041100000059")
            # spi.order_cancel2("CZCE", "CF411", 1, -1111111, "3")

            # 请求查询交易编码
            # spi.qry_trading_code("CZCE")

            # 查询交易所
            # spi.qry_exchange("DCE")

            #查询交易者持仓
            spi.qry_investor_position()

            #查询交易者持仓明细
            # spi.qry_investor_position_detail("jd2409")

            # spi.user_password_update("sWJedore20@#0808", "sWJedore20@#0807")
            # spi.qry_order_comm_rate("ss2407")
            break

    spi.wait()
