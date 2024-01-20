from django.db import models

# Create your models here.
# from django.contrib.auth.models import User
from django.conf import settings


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
#
#
# class Strategy(models.Model):
#     name = models.CharField(max_length=120, unique=True, verbose_name="策略名称")
#
#     TIME_CYCLE_CHOICES = [
#         ('1m', '1分钟'),
#         ('5m', '5分钟'),
#         ('15m', '15分钟'),
#         ('30m', '30分钟'),
#         ('1h', '1小时'),
#         ('2h', '2小时'),
#         ('4h', '4小时'),
#         ('6h', '6小时'),
#         ('12h', '12小时'),
#         ('1d', '1天'),
#         ('1w', '1周'),
#     ]
#     strategy_time_cycle = models.CharField(choices=TIME_CYCLE_CHOICES, max_length=50, verbose_name="策略应用时间周期")
#     strategy_desc = models.TextField(max_length=255, blank=True, verbose_name="策略描述")
#
#     status = models.BooleanField(default=True, verbose_name="策略状态")
#     create_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
#     update_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")
#     stra_creater = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="策略创建者")
#
#     class Meta:
#         db_table = 'strategy'
#         verbose_name = '交易策略'
#         verbose_name_plural = verbose_name
#         ordering = ('-update_time',)
#
#     def __str__(self):
#         return self.name
