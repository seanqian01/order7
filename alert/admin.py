from django.contrib import admin
from django.http import HttpRequest
from alert.models import stra_Alert, Strategy, Merchant, User, Exchange, ContractCode, OrderRecord
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
                    'strategy_id',
                    'created_at',
                    ]
    list_filter = ('created_at', 'time_circle', 'scode', 'contractType', 'strategy_id','status')
    search_fields = ['scode', 'price']
    list_per_page = 30
    ordering = ('-created_at',)
    actions = ['export_selected']

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
    list_display = ['id','strategy_name', 'status', 'strategy_time_cycle', 'stra_creater', 'update_time', 'create_time', ]
    list_filter = ('strategy_name', 'status', 'strategy_time_cycle',)
    list_per_page = 30

    def get_list_display_links(self, request, list_display):
        return ("strategy_name")

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

@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['name', 'code']

@admin.register(ContractCode)
class ContractCodeAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'exchange', 'name', 'product_type', 'min_size', 'size_increment', 'price_precision', 'size_precision', 'is_active']
    list_filter = ['exchange', 'product_type', 'is_active']
    search_fields = ['symbol', 'name']
    raw_id_fields = ['exchange']

admin.site.register(Strategy, StrategyAdmin)

admin.site.register(stra_Alert, AlertAdmin)

admin.site.register(Merchant, MerchantAdmin)

admin.site.register(User, MyUserAdmin)

# 订单记录的只读Admin界面
class OrderRecordAdmin(admin.ModelAdmin):
    list_display = [
        'order_id','oid', 'symbol', 'side','order_type', 'price', 'quantity', 
        'filled_quantity', 'status',  'is_stop_loss',
         'fee',  'filled_time', 'create_time'
    ]
    list_filter = ['status', 'side', 'is_stop_loss', 'reduce_only', 'order_type', 'create_time']
    search_fields = ['order_id', 'symbol', 'oid']
    readonly_fields = [
        'order_id', 'symbol', 'side', 'price', 'quantity', 
        'filled_quantity', 'status', 'reduce_only', 'is_stop_loss',
        'oid', 'fee', 'order_type', 'filled_time', 'create_time', 'update_time'
    ]
    # 移除date_hierarchy以避免时区问题
    # date_hierarchy = 'create_time'
    list_per_page = 50
    ordering = ('-create_time',)
    
    # 添加批量更新订单详情的操作
    actions = ['update_order_details']
    
    def update_order_details(self, request, queryset):
        """批量更新选中订单的详细信息"""
        from alert.core.async_order_record import start_order_update_thread
        count = 0
        for order in queryset:
            start_order_update_thread(order.id)
            count += 1
        self.message_user(request, f"已启动{count}个订单的详情更新任务，请稍后刷新页面查看结果。")
    update_order_details.short_description = "更新选中订单的详细信息"
    
    # 添加单个订单详情更新按钮
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/update_details/',
                self.admin_site.admin_view(self.update_single_order_details),
                name='alert_orderrecord_update_details',
            ),
        ]
        return custom_urls + urls
    
    def update_single_order_details(self, request, object_id, *args, **kwargs):
        """手动更新单个订单的详细信息"""
        from alert.core.async_order_record import manually_update_order_details
        from django.http import HttpResponseRedirect
        from django.contrib import messages
        from django.urls import reverse
        
        result = manually_update_order_details(object_id)
        
        if result["status"] == "success":
            messages.success(request, f"订单详情更新成功: {result['message']}")
        else:
            messages.error(request, f"订单详情更新失败: {result['message']}")
        
        # 重定向回订单详情页面
        return HttpResponseRedirect(
            reverse('admin:alert_orderrecord_change', args=(object_id,))
        )
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """添加更新详情按钮到订单详情页面"""
        from django.urls import reverse
        from django.utils.safestring import mark_safe
        
        extra_context = extra_context or {}
        
        # 创建更新按钮的HTML
        update_url = reverse('admin:alert_orderrecord_update_details', args=[object_id])
        update_button = f'''
        <div style="margin-top: 20px; text-align: center;">
            <a href="{update_url}" class="button" 
               style="background-color: #417690; color: white; padding: 10px 15px; border: none; border-radius: 4px; font-weight: bold; text-decoration: none;">
                手动更新订单详情
            </a>
        </div>
        '''
        
        # 使用Django的admin自定义方式添加按钮
        extra_context['after_field_sets'] = mark_safe(update_button)
        
        return super().change_view(request, object_id, form_url, extra_context)
    
    # 允许查看详情
    def has_view_permission(self, request, obj=None):
        return True
    
    # 禁止添加
    def has_add_permission(self, request):
        return False
    
    # 允许修改页面访问，但表单是只读的
    def has_change_permission(self, request, obj=None):
        return True
    
    # 禁止删除
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(OrderRecord, OrderRecordAdmin)
