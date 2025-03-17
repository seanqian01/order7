from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alert', '0019_alter_orderrecord_avg_price_alter_orderrecord_fee_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE stra_Alert MODIFY COLUMN price DECIMAL(20,5)',
            reverse_sql='ALTER TABLE stra_Alert MODIFY COLUMN price DECIMAL(20,2)'
        ),
    ]
