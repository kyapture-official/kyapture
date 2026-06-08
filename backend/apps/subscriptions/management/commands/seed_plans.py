from django.core.management.base import BaseCommand
from apps.subscriptions.models import SubscriptionPlan


class Command(BaseCommand):
    """
    Django administrative management command to seed baseline subscription plans.
    Idempotent execution prevents duplicate record generation on consecutive runs [1.1.2].
    Run via: python manage.py seed_plans
    """
    help = 'Seeds the database with standard, production-ready Kyapture subscription plans.'

    def handle(self, *args, **kwargs):
        plans = [
            {
                'name': 'Basic',
                'price': '9.99',
                'max_galleries': 3,
                'max_photos_per_gallery': 100,
                'storage_gb': 5,
            },
            {
                'name': 'Pro',
                'price': '24.99',
                'max_galleries': 20,
                'max_photos_per_gallery': 500,
                'storage_gb': 50,
            },
            {
                'name': 'Studio',
                'price': '59.99',
                'max_galleries': 100,
                'max_photos_per_gallery': 2000,
                'storage_gb': 200,
            },
        ]

        for plan_data in plans:
            # get_or_create ensures safe, repeatable seed execution [1.1.2]
            plan, created = SubscriptionPlan.objects.get_or_create(
                name=plan_data['name'],
                defaults=plan_data
            )
            status_text = 'Created' if created else 'Already exists'
            self.stdout.write(f'{status_text}: {plan.name} — ${plan.price}/mo')

        self.stdout.write(
            self.style.SUCCESS('Successfully synchronized subscription plan seed data.')
        )