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
    strategy_desc = models.TextField(blank=True, verbose_name="策略描述")
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
    # 修改精度为5位小数，确保能够存储更精确的价格
    price = models.DecimalField(max_digits=20, decimal_places=5, verbose_name="价格")
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

    ORDER_STATUS_CHOICES = (
        ('PENDING', '待处理'),
        ('SUBMITTED', '已委托'),
        ('FILLED', '已成交'),
        ('CANCELLED', '已撤销'),
        ('FAILED', '失败'),
    )
    status = models.CharField(max_length=50, choices=ORDER_STATUS_CHOICES, default='PENDING', verbose_name='订单状态')

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


class Exchange(models.Model):
    """交易所配置"""
    name = models.CharField('交易所名称', max_length=50)
    code = models.CharField('交易所代码', max_length=20, unique=True)
    description = models.TextField('描述', blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '交易所'
        verbose_name_plural = verbose_name
        ordering = ['code']

    def __str__(self):
        return self.name

class ContractCode(models.Model):
    """交易对配置"""
    PRODUCT_TYPES = [
        ('spot', '现货'),
        ('perpetual', '永续合约'),
    ]
    
    exchange = models.ForeignKey(Exchange, on_delete=models.CASCADE, related_name='contracts', verbose_name='交易所')
    symbol = models.CharField('交易对象符号', max_length=20)
    name = models.CharField('交易对象名称', max_length=50)
    description = models.CharField('描述', max_length=100, blank=True)
    product_type = models.CharField('产品类型', max_length=20, choices=PRODUCT_TYPES, default='perpetual')
    min_size = models.DecimalField('最小下单数量', max_digits=18, decimal_places=8)
    size_increment = models.IntegerField('数量增量', default=1)
    price_precision = models.IntegerField('价格精度')
    size_precision = models.IntegerField('数量精度')
    default_quantity = models.DecimalField('默认下单数量', max_digits=18, decimal_places=5, default=1.0)
    stop_loss_percentage = models.DecimalField('止损百分比', max_digits=5, decimal_places=1, default=8.0, help_text='止损百分比，默认为8%')
    stop_loss_slippage = models.DecimalField('止损单滑点', max_digits=4, decimal_places=2, default=0.5, help_text='止损单滑点百分比，默认为0.5%')
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    def __str__(self):
        return f"{self.exchange.name} - {self.name} ({self.get_product_type_display()})"

    class Meta:
        verbose_name = '交易对'
        verbose_name_plural = verbose_name
        unique_together = ['exchange', 'symbol']
        ordering = ['exchange', 'symbol']



class OrderRecord(models.Model):
    """订单记录表"""
    ORDER_STATUS = (
        ('PENDING', '待成交'),
        ('PARTIALLY_FILLED', '部分成交'),
        ('FILLED', '已完成'),
        ('CANCELLED', '已取消'),
        ('REJECTED', '已拒绝'),
    )
    
    ORDER_TYPES = (
        ('OPEN', '开仓单'),
        ('CLOSE', '平仓单'),
    )

    order_id = models.CharField('订单ID', max_length=50)
    symbol = models.CharField('交易对', max_length=20)
    side = models.CharField('方向', max_length=10)
    quantity = models.DecimalField('数量', max_digits=18, decimal_places=5)
    price = models.DecimalField('价格', max_digits=18, decimal_places=8)
    status = models.CharField('状态', max_length=20, choices=ORDER_STATUS, default='PENDING')
    filled_quantity = models.DecimalField('已成交数量', max_digits=18, decimal_places=5, null=True, blank=True)
    avg_price = models.DecimalField('成交均价', max_digits=18, decimal_places=5, null=True, blank=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)
    reduce_only = models.BooleanField('是否只减仓', default=False)  
    is_stop_loss = models.BooleanField('是否是止损单', default=False)  
    
    # 新增字段
    oid = models.CharField('渠道订单ID', max_length=50, null=True, blank=True, help_text='交易所平台的原始订单ID')
    fee = models.DecimalField('手续费', max_digits=18, decimal_places=2, null=True, blank=True, help_text='订单成交的手续费')
    order_type = models.CharField('订单类型', max_length=20, choices=ORDER_TYPES, default='UNKNOWN', help_text='订单类型：开仓单，平仓单')
    filled_time = models.DateTimeField('成交时间', null=True, blank=True, help_text='订单成交时间')

    class Meta:
        db_table = 'order_record'
        verbose_name = '订单记录'
        verbose_name_plural = '订单记录'
        indexes = [
            models.Index(fields=['symbol', 'create_time']),
            models.Index(fields=['status', 'create_time']),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.order_id}"