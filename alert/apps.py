from django.apps import AppConfig
from alert.core.init import initialize_application

class AlertConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alert'
    verbose_name = '交易管理'
    
    def ready(self):
        # 应用启动时初始化
        initialize_application()