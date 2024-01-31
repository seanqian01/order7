from django.urls import path
from rest_framework.authtoken import views
from alert.view import signal, stra_view, merchant, user
from django.core.signals import request_finished

urlpatterns = [
    path('webhook/', signal.webhook, name='webhook'),
    # 策略相关路由
    path('stra/list/', stra_view.strategy_list, name='Strategy List'),
    path('stra/detail/<int:pk>/', stra_view.strategy_detail, name='Strategy Detail'),
    # 商户相关路由
    path('merchant/list/', merchant.merchantlist, name='Merchant List'),
    path('merchant/detail/<int:pk>/', merchant.merchantdetail, name='Merchant Detail'),

    path('api/token-auth/', views.obtain_auth_token, name='Token Create'),
    path('login/', user.LoginView.as_view(), name='User Login'),

]

# 在 Django 项目退出时调用 on_exit 函数
request_finished.connect(signal.on_exit)
