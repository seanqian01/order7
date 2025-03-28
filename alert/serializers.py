from rest_framework import serializers

from .models import Strategy, Merchant
from django.contrib.auth.models import User


class StrategySerializer(serializers.ModelSerializer):
    stra_creater = serializers.ReadOnlyField(source='stra_creater.username')

    class Meta:
        model = Strategy
        fields = '__all__'
        # depth = 2


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # fields = ['id', 'username', 'strategies']
        fields = '__all__'


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        # fields = ['id', 'username', 'merchants']
        fields = '__all__'
