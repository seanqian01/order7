from django.urls import path

from alert import views, stra_view

urlpatterns = [
    path('webhook/', views.webhook, name='webhook'),
    path('stra/list/', stra_view.strategy_list, name='Strategy List'),
]
