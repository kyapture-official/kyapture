# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/management/commands/seed_plans.py
from django.core.management.base import BaseCommand
from apps.subscriptions.models import SubscriptionPlan


class Command(BaseCommand):
    """
    Plans are DATA, not code: they are seeded once by migration
    subscriptions.0005_seed_plans_dummy (dummy NPR values) and edited by the
    owner in Django admin. This command no longer carries any prices — it only
    guarantees the Free-tier row exists and lists what the plan table holds.
    Run via: python manage.py seed_plans
    """
    help = 'Ensures the Free plan row exists and lists the plan table (edit values in Django admin).'

    def handle(self, *args, **kwargs):
        SubscriptionPlan.get_free()
        for plan in SubscriptionPlan.objects.order_by('price'):
            self.stdout.write(f'{plan.key}: {plan}')
        self.stdout.write(self.style.SUCCESS('Plan table is the single source of truth — edit it in Django admin.'))
