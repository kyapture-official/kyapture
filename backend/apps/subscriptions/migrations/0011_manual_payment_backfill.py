# Data step of chunk 7.5-B. Kept apart from the schema steps: PostgreSQL refuses to build an index in
# the same transaction as an UPDATE on a table with pending foreign-key trigger events.
from django.db import migrations


LEGACY_PROOF_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}


def backfill_legacy_payments(apps_, schema_editor):
    """
    Payments from before 7.5-B: the price at submission is the amount they were accepted at (the old
    submit refused any amount other than the plan price), a reviewed row was reviewed when it was last
    saved, and the proof type follows the stored extension (those uploads were images only).
    """
    from django.db.models import F
    ManualPayment = apps_.get_model('subscriptions', 'ManualPayment')
    ManualPayment.objects.update(plan_price=F('amount'))
    ManualPayment.objects.exclude(status='pending').update(reviewed_at=F('updated_at'))
    for payment in ManualPayment.objects.exclude(payment_proof=''):
        name = str(payment.payment_proof.name).lower()
        proof_type = next((kind for ext, kind in LEGACY_PROOF_TYPES.items() if name.endswith(ext)), '')
        if proof_type:
            ManualPayment.objects.filter(pk=payment.pk).update(proof_type=proof_type)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0010_manual_payment_review'),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_payments, migrations.RunPython.noop),
    ]
