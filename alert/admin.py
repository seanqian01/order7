from django.contrib import admin
from alert.models import stra_Alert, Strategy, Merchant, User
from django.contrib.auth.admin import UserAdmin
import logging

logger = logging.getLogger(__name__)

admin.site.site_header = "sean_量化交易管理系统"
admin.site.site_title = "量化交易管理系统--sean"


# @admin.register(stra_Alert)
class AlertAdmin(admin.ModelAdmin):
    ordering = ('-created_at',)
    list_display = ['alert_title',
                    'symbol',
                    'scode',
                    'contractType',
                    'price',
                    'action',
                    'status',
                    'created_at',
                    ]
    list_filter = ('created_at', 'symbol', 'contractType', 'action')
    list_per_page = 30

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
