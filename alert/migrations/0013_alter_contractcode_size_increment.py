# Generated by Django 4.1 on 2025-03-10 15:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0012_contractcode_stop_loss_percentage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contractcode',
            name='size_increment',
            field=models.IntegerField(default=1, verbose_name='数量增量'),
        ),
    ]
