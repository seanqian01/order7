# Generated by Django 4.1 on 2024-02-02 10:23

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stra_alert',
            name='time_circle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='alert.timecycle', verbose_name='时间周期'),
        ),
        migrations.AlterField(
            model_name='stra_alert',
            name='status',
            field=models.BooleanField(blank=True, default=False, verbose_name='有效性'),
        ),
        migrations.AlterField(
            model_name='user',
            name='sid',
            field=models.CharField(blank=True, max_length=24, verbose_name='身份证'),
        ),
    ]
