from django.contrib import admin

from alert.models import stra_Alert, Strategy, Merchant, User, TimeCycle
from django.contrib.auth.admin import UserAdmin
import logging
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields, widgets

logger = logging.getLogger(__name__)

admin.site.site_header = "sean_量化交易管理系统"
admin.site.site_title = "量化交易管理系统--sean"


class stra_AlertResource(resources.ModelResource):
    price = fields.Field(attribute='price', column_name='价格')
    # symbol = fields.Field(attribute='symbol', column_name='名称')
    scode = fields.Field(attribute='scode', column_name='代码')
    alert_title = fields.Field(attribute='alert_title', column_name='信号描述')
    contractType = fields.Field(attribute='contractType', column_name='交易合约类型')
    action = fields.Field(attribute='action', column_name='交易方向')
    status = fields.Field(attribute='status', column_name='有效性')
    time_circle = fields.Field(attribute='time_circle', column_name='时间周期')
    created_at = fields.Field(attribute='created_at', column_name='触发时间',
                              widget=widgets.DateTimeWidget(format='%Y-%m-%d %H:%M:%S'))

    def before_import_row(self, row, **kwargs):
        # 处理导入前的每一行数据
        time_circle_str = row.get('时间周期')

        # 尝试通过名称获取或创建TimeCycle实例
        try:
            time_circle = TimeCycle.objects.get(name=time_circle_str)
        except TimeCycle.DoesNotExist:
            # 如果找不到对应的TimeCycle记录，你可能需要根据实际情况处理，例如创建一个默认的TimeCycle
            # 这里简单地将时间周期设置为None
            time_circle = None

        row['时间周期'] = time_circle

    class Meta:
        model = stra_Alert
        fields = (
            'alert_title', 'scode', 'contractType', 'price', 'action', 'status', 'created_at', 'time_circle')
        export_order = (
            'alert_title', 'scode', 'contractType', 'price', 'action', 'status', 'created_at', 'time_circle')
        skip_unchanged = True
        import_id_fields = ['alert_title', 'scode', 'contractType', 'price', 'action', 'status', 'created_at',
                            'time_circle']


# @admin.register(stra_Alert)
class AlertAdmin(ImportExportModelAdmin):
    resource_class = stra_AlertResource
    list_display = ['alert_title',
                    'time_circle',
                    'symbol',
                    'scode',
                    'contractType',
                    'price',
                    'action',
                    'status',
                    'created_at',
                    ]
    list_filter = ('created_at', 'time_circle', 'scode', 'contractType', 'action')
    search_fields = ['scode', 'price']
    list_per_page = 30
    ordering = ('-created_at',)
    actions = ['export_selected']

    # def export_selected(self, request, queryset):
    #     # 导出选中的结果到Excel
    #     from import_export.admin import ExportActionModelAdmin
    #
    #     exporter = ExportActionModelAdmin()
    #     return exporter.export_excel_action(modeladmin=self, request=request, queryset=queryset)

    def export_selected(self, request, queryset):
        # 导出选中的结果到Excel
        return self.export_action(modeladmin=self, request=request, queryset=queryset)

    export_selected.short_description = "导出选中项到Excel"

    class Media:
        def __init__(self):
            pass

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class StrategyAdmin(admin.ModelAdmin):
    list_display = ['strategy_name', 'status', 'strategy_time_cycle', 'stra_creater', 'update_time', 'create_time', ]
    list_filter = ('strategy_name', 'status', 'strategy_time_cycle',)
    list_per_page = 30

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    class Media:
        def __init__(self):
            pass


class MerchantAdmin(admin.ModelAdmin):
    list_display = ['merchant_name', 'merchant_email', 'merchant_id', 'merchant_status',
                    'merchant_update_time', 'merchant_create_time', ]
    list_filter = ('merchant_name', 'merchant_email', 'merchant_id', 'merchant_status')
    list_per_page = 20

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MyUserAdmin(UserAdmin):
    list_display = ['username', 'name', 'email', 'is_staff', 'is_active', 'telephone',
                    'user_type', 'date_joined', ]
    list_filter = ('username', 'email', 'is_active', 'telephone', 'sid')
    list_per_page = 20
    fieldsets = ()

    add_fieldsets = (
        (
            None, {
                'classes': ('wide',),
                'fields': (
                    'username', 'password1', 'password2', 'email', 'is_staff', 'is_active', 'telephone', 'user_type',
                    'sid',),
            }
        ),
    )

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    class Media:
        def __init__(self):
            pass


admin.site.register(Strategy, StrategyAdmin)

admin.site.register(stra_Alert, AlertAdmin)

admin.site.register(Merchant, MerchantAdmin)

admin.site.register(User, MyUserAdmin)
