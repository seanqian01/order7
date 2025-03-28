# Generated by Django 4.1 on 2025-03-10 15:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0013_alter_contractcode_size_increment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractcode',
            name='default_quantity',
            field=models.DecimalField(decimal_places=5, default=1.0, max_digits=18, verbose_name='默认下单数量'),
        ),
        migrations.AlterField(
            model_name='contractcode',
            name='stop_loss_percentage',
            field=models.DecimalField(decimal_places=1, default=10.0, help_text='止损百分比，默认为10%', max_digits=5, verbose_name='止损百分比'),
        ),
    ]
