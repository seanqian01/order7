from django.contrib import admin
from alert.models import stra_Alert, Strategy, Merchant, User
from django.contrib.auth.admin import UserAdmin
import logging
from import_export.admin import ImportExportModelAdmin, ExportActionModelAdmin
from import_export import resources, fields
from django.contrib.admin.models import LogEntry

logger = logging.getLogger(__name__)

admin.site.site_header = "vcpos_量化交易管理系统"
admin.site.site_title = "量化交易管理系统--vcpos"


class stra_AlertResource(resources.ModelResource):
    price = fields.Field(attribute='price', column_name='价格')
    alert_title = fields.Field(attribute='alert_title', column_name='信号描述')
    contractType = fields.Field(attribute='contractType', column_name='交易合约类型')

    class Meta:
        model = stra_Alert
        fields = (
            'alert_title', 'symbol', 'scode', 'contractType', 'price', 'action', 'status', 'created_at', 'time_circle')
        export_order = (
            'alert_title', 'symbol', 'scode', 'contractType', 'price', 'action', 'status', 'created_at', 'time_circle')


# @admin.register(stra_Alert)
class AlertAdmin(ImportExportModelAdmin, ExportActionModelAdmin):
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
    list_filter = ('created_at', 'time_circle', 'scode', 'contractType', 'action','status')
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


#用户日志
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ['action_time', 'user', 'content_type', 'object_repr', 'action_flag', 'change_message']
    search_fields = ['user__username', 'object_repr', 'change_message']
    list_filter = ['action_time', 'user', 'content_type', 'action_flag']

admin.site.register(Strategy, StrategyAdmin)

admin.site.register(stra_Alert, AlertAdmin)

admin.site.register(Merchant, MerchantAdmin)

admin.site.register(User, MyUserAdmin)
