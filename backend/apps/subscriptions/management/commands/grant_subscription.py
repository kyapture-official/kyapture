# C:/Users/LENOVO/Desktop/kyapture/backend/apps/subscriptions/management/commands/grant_subscription.py
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.users.models import User
from apps.subscriptions.models import SubscriptionPlan, UserSubscription


class Command(BaseCommand):
    help = "Grants (or renews) an active subscription for local/dev testing."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)
        parser.add_argument("--plan", type=str, default="Pro")
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        email = options["email"].strip().lower()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        # Dev helper: use the real plan row from the plan table (edited in
        # admin). It never invents a plan or its limits.
        name = options["plan"].strip()
        plan = SubscriptionPlan.objects.filter(name__iexact=name).first()
        if plan is None:
            available = ", ".join(SubscriptionPlan.objects.values_list("name", flat=True)) or "none"
            raise CommandError(f"No plan named '{name}'. Plans in the table: {available}")

        now = timezone.now()
        sub, _ = UserSubscription.objects.update_or_create(
            user=user,
            defaults={
                "plan": plan,
                "status": UserSubscription.SubscriptionStatus.ACTIVE,
                "payment_method": UserSubscription.PaymentMethod.MANUAL,
                "starts_at": now,
                "expires_at": now + timedelta(days=options["days"]),
                # a new period: the lifecycle markers of the old one are cleared (7.5-C)
                **{marker: None for marker in UserSubscription.LIFECYCLE_MARKERS},
            },
        )

        user.is_active_plan = True
        user.save(update_fields=["is_active_plan"])

        self.stdout.write(self.style.SUCCESS(
            f"Granted '{plan.name}' to {user.email} — expires {sub.expires_at:%Y-%m-%d}"
        ))