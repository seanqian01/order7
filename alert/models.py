from django.db import models


# Create your models here.
# from django.contrib.auth.models import User


class stra_Alert(models.Model):
    alert_title = models.CharField(null=True, max_length=255, verbose_name="信号描述")
    symbol = models.CharField(null=True, max_length=70, verbose_name="名称")
    scode = models.CharField(null=True, max_length=30, verbose_name="代码")
    C_TYPE = [
        (1, "商品期货"),
        (2, "股票"),
        (3, "虚拟货币"),
    ]
    contractType = models.IntegerField(choices=C_TYPE, blank=True, null=True, verbose_name="交易合约类型")
    price = models.DecimalField(max_digits=20, decimal_places=2, verbose_name="价格")
    action = models.CharField(max_length=100, verbose_name="交易方向")
    status = models.BooleanField(default=False, blank=True, verbose_name="状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="触发时间")

    def __str__(self):
        return self.symbol

    @property
    def status_display(self):
        return "有效" if self.status else "无效"

    class Meta:
        db_table = 'stra_Alert'
        verbose_name = '交易信号提醒'
        verbose_name_plural = verbose_name


class stra_Order(models.Model):
    exchange = models.CharField(max_length=50, verbose_name="交易所")
    symbol = models.CharField(max_length=50, verbose_name="交易对")
    type = models.CharField(max_length=50, verbose_name="订单类型")
    side = models.CharField(max_length=50, verbose_name="买卖方向")
    amount = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="交易数量")
    price = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="价格")
    filled = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="已成交数量")
    remaining = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="剩余数量")
    status = models.CharField(max_length=50, verbose_name="订单状态")
    timestamp = models.DateTimeField(verbose_name="订单时间")

    class Meta:
        db_table = 'stra_order'
        verbose_name = '交易订单'
        verbose_name_plural = verbose_name
