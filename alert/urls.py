from django.urls import path

from alert import views

urlpatterns = [
    path('webhook/', views.webhook, name='webhook'),
]
