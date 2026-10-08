# One live claim per transaction id (chunk 7.5-B): see ManualPayment.Meta.constraints.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0011_manual_payment_backfill'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='manualpayment',
            constraint=models.UniqueConstraint(condition=models.Q(models.Q(('status', 'rejected'), _negated=True), models.Q(('reference_key', ''), _negated=True)), fields=('reference_key',), name='uniq_manual_pay_reference'),
        ),
    ]
