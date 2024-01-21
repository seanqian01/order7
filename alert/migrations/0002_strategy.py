# Generated by Django 4.1 on 2024-01-21 16:37

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('alert', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Strategy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('strategy_name', models.CharField(max_length=120, unique=True, verbose_name='策略名称')),
                ('strategy_time_cycle', models.CharField(choices=[('1m', '1分钟'), ('5m', '5分钟'), ('15m', '15分钟'), ('30m', '30分钟'), ('1h', '1小时'), ('2h', '2小时'), ('4h', '4小时'), ('6h', '6小时'), ('12h', '12小时'), ('1d', '1天'), ('1w', '1周')], max_length=50, verbose_name='策略应用时间周期')),
                ('strategy_desc', models.TextField(blank=True, max_length=255, verbose_name='策略描述')),
                ('status', models.BooleanField(default=True, verbose_name='策略状态')),
                ('create_time', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('update_time', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('stra_creater', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='策略创建者')),
            ],
            options={
                'verbose_name': '交易策略',
                'verbose_name_plural': '交易策略',
                'db_table': 'strategy',
                'ordering': ('-update_time',),
            },
        ),
    ]
