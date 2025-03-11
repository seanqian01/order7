# Generated by Django 4.1 on 2025-03-11 12:52

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0016_contractcode_stop_loss_slippage_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='orderrecord',
            name='order_recor_symbol_4d9c23_idx',
        ),
        migrations.RemoveIndex(
            model_name='orderrecord',
            name='order_recor_status_b702fa_idx',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='cloid',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='created_at',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='last_retry_time',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='order_type',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='position_type',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='retry_count',
        ),
        migrations.RemoveField(
            model_name='orderrecord',
            name='updated_at',
        ),
        migrations.AddField(
            model_name='orderrecord',
            name='avg_price',
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True, verbose_name='成交均价'),
        ),
        migrations.AddField(
            model_name='orderrecord',
            name='create_time',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now, verbose_name='创建时间'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='orderrecord',
            name='reduce_only',
            field=models.BooleanField(default=False, verbose_name='是否只减仓'),
        ),
        migrations.AddField(
            model_name='orderrecord',
            name='update_time',
            field=models.DateTimeField(auto_now=True, verbose_name='更新时间'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='filled_quantity',
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=18, null=True, verbose_name='已成交数量'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='is_stop_loss',
            field=models.BooleanField(default=False, verbose_name='是否是止损单'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='order_id',
            field=models.CharField(max_length=50, verbose_name='订单ID'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='price',
            field=models.DecimalField(decimal_places=8, max_digits=18, verbose_name='价格'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='quantity',
            field=models.DecimalField(decimal_places=8, max_digits=18, verbose_name='数量'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='side',
            field=models.CharField(max_length=10, verbose_name='方向'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='status',
            field=models.CharField(choices=[('PENDING', '待成交'), ('PARTIALLY_FILLED', '部分成交'), ('FILLED', '已完成'), ('CANCELLED', '已取消'), ('REJECTED', '已拒绝')], default='PENDING', max_length=20, verbose_name='状态'),
        ),
        migrations.AlterField(
            model_name='orderrecord',
            name='symbol',
            field=models.CharField(max_length=20, verbose_name='交易对'),
        ),
        migrations.AddIndex(
            model_name='orderrecord',
            index=models.Index(fields=['symbol', 'create_time'], name='order_recor_symbol_e1f35b_idx'),
        ),
        migrations.AddIndex(
            model_name='orderrecord',
            index=models.Index(fields=['status', 'create_time'], name='order_recor_status_5cc05e_idx'),
        ),
    ]
