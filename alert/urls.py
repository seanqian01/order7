from django.urls import path
from rest_framework.authtoken import views
from alert.view import signal, stra_view

urlpatterns = [
    path('webhook/', signal.webhook, name='webhook'),
    path('stra/list/', stra_view.strategy_list, name='Strategy List'),
    path('stra/detail/<int:pk>/', stra_view.strategy_detail, name='Strategy Detail'),

    path('api/token-auth/', views.obtain_auth_token, name='Token Create'),
]
