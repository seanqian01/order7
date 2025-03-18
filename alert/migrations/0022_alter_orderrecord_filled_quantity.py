# Generated by Django 5.1.7 on 2025-03-18 01:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0021_orderrecord_filled_price_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderrecord',
            name='filled_quantity',
            field=models.DecimalField(blank=True, decimal_places=5, max_digits=18, null=True, verbose_name='已成交数量'),
        ),
    ]
