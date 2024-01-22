from django.contrib import admin
from alert.models import stra_Alert, Strategy
from django.utils.html import format_html
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
    list_display = ['strategy_name', 'status', 'strategy_time_cycle', 'update_time', 'create_time', ]
    list_filter = ('strategy_name', 'status', 'strategy_time_cycle',)
    list_per_page = 30

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    class Media:
        def __init__(self):
            pass


admin.site.register(Strategy, StrategyAdmin)

admin.site.register(stra_Alert, AlertAdmin)
