from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class TimeCycle(models.Model):
    name = models.CharField(max_length=20, verbose_name="应用周期名称")

    class Meta:
        db_table = 'TimeCycle'

    def __str__(self):
        return self.name


class User(AbstractUser):
    # 用户类型
    user_type_choices = (
        (1, "系统管理员"),
        (2, "普通用户"),
        (3, "商户管理员"),
    )
    user_type = models.PositiveSmallIntegerField(default=2, choices=user_type_choices, verbose_name="用户类型")
    telephone = models.CharField(max_length=11, verbose_name='手机号码')
    name = models.CharField(max_length=12, verbose_name='用户姓名')
    sid = models.CharField(max_length=24, blank=True, verbose_name='身份证')

    class Meta:
        db_table = 'User'
        verbose_name = '系统用户'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.username


class Strategy(models.Model):
    strategy_name = models.CharField(max_length=120, unique=True, verbose_name="策略名称")

    # TIME_CYCLE_CHOICES = [
    #     ('1m', '1分钟'),
    #     ('5m', '5分钟'),
    #     ('15m', '15分钟'),
    #     ('30m', '30分钟'),
    #     ('1h', '1小时'),
    #     ('2h', '2小时'),
    #     ('4h', '4小时'),
    #     ('6h', '6小时'),
    #     ('12h', '12小时'),
    #     ('1d', '1天'),
    #     ('1w', '1周'),
    # ]
    strategy_time_cycle = models.ForeignKey(TimeCycle, on_delete=models.CASCADE, verbose_name="策略时间周期")
    strategy_desc = models.TextField(max_length=255, blank=True, verbose_name="策略描述")
    status = models.BooleanField(default=True, verbose_name="策略状态")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    update_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    stra_creater = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="策略创建者")

    class Meta:
        db_table = 'strategy'
        verbose_name = '交易策略'
        verbose_name_plural = verbose_name
        ordering = ('-update_time',)

    def __str__(self):
        return self.strategy_name

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
    status = models.BooleanField(default=False, blank=True, verbose_name="有效性")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="触发时间")
    time_circle = models.ForeignKey(TimeCycle, on_delete=models.CASCADE, null=True, blank=True, verbose_name="时间周期")
    strategy_id = models.ForeignKey(Strategy, on_delete=models.CASCADE, null=True, blank=True, verbose_name="策略ID")

    def __str__(self):
        return self.scode

    class Meta:
        db_table = 'stra_Alert'
        verbose_name = '交易信号提醒'
        verbose_name_plural = verbose_name


class stra_Order(models.Model):
    exchange = models.CharField(max_length=50, verbose_name="交易所")
    symbol = models.CharField(max_length=50, verbose_name="交易对")
    ORDER_TYPE_CHOICES = [
        ('limit', "限价单"),
        ('market', "市价单"),
        ('stop_loss', "止损单"),
        # 可以根据需求添加更多类型
    ]
    type = models.CharField(max_length=50, choices=ORDER_TYPE_CHOICES, verbose_name="订单类型")    
    SIDE_CHOICES = [
        ('buy', "买入"),
        ('sell', "卖出"),
    ]
    side = models.CharField(max_length=50, choices=SIDE_CHOICES, verbose_name="买卖方向")
    amount = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="交易数量")
    price = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="价格")
    filled = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="已成交数量")
    remaining = models.DecimalField(max_digits=18, decimal_places=8, verbose_name="剩余数量")

    ORDER_STATUS_CHOICES = [
        ('pending', "待处理"),
        ('partially_filled', "部分成交"),
        ('filled', "完全成交"),
        ('cancelled', "已取消"),
        ('failed', "失败"),
    ]
    status = models.CharField(max_length=50, choices=ORDER_STATUS_CHOICES, verbose_name="订单状态")

    timestamp = models.DateTimeField(verbose_name="订单时间")
    POSITION_ACTION_CHOICES = [
        (1, "开仓"),
        (0, "平仓"),
    ]
    position_action = models.CharField(max_length=50, choices=POSITION_ACTION_CHOICES, verbose_name="开仓/平仓")
    order_id = models.CharField(max_length=100, unique=True, verbose_name="订单ID")

    class Meta:
        db_table = 'stra_order'
        verbose_name = '交易订单'
        verbose_name_plural = verbose_name




# 商户类型表
class MerchantStyle(models.Model):
    merchant_style_name = models.CharField(max_length=120, unique=True, verbose_name="商户类型名称")

    class Meta:
        db_table = 'merchant_style'
        verbose_name = '商户类型'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.merchant_style_name


# 商户基本信息表
class Merchant(models.Model):
    merchant_name = models.CharField(max_length=120, unique=True, verbose_name="商户名称")
    merchant_address = models.TextField(max_length=255, blank=True, verbose_name="商户地址")
    merchant_phone = models.CharField(max_length=11, unique=True, verbose_name="商户联系电话")
    merchant_email = models.EmailField(max_length=120, unique=True, verbose_name="商户联系邮箱")
    merchant_web = models.URLField(max_length=120, unique=True, verbose_name="商户网站")
    merchant_id = models.CharField(max_length=120, unique=True, verbose_name="商户ID编号")
    merchant_status = models.BooleanField(default=True, verbose_name="商户状态")
    merchant_style = models.ForeignKey(MerchantStyle, on_delete=models.CASCADE, verbose_name="商户类型")
    merchant_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="商户管理员")
    merchant_create_time = models.DateTimeField(auto_now_add=True, verbose_name="商户创建时间")
    merchant_update_time = models.DateTimeField(auto_now=True, verbose_name="商户更新时间")

    class Meta:
        db_table = 'merchant'
        verbose_name = '商户基本信息'
        verbose_name_plural = verbose_name
        ordering = ('-merchant_update_time',)

    def __str__(self):
        return self.merchant_name
