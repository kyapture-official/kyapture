# docs/qa-7e/seed_7e.py - 7-E QA accounts. Run: docker exec -e QA_TS=<stamp> -e QA_PW=<pw> kyapture-backend-1 sh -c "python manage.py shell < /tmp/seed_7e.py"
# Prints CREATED_USER ids: delete exactly those ids afterwards (cascade), then that user's media folder.
import os
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.subscriptions.models import SubscriptionPlan, UserSubscription

ts = os.environ['QA_TS']
pw = os.environ['QA_PW']
User = get_user_model()
pro = User.objects.create_user(email=f'qa7e-pro-{ts}@example.invalid', username=f'qa7epro{ts}', password=pw)
print('CREATED_USER', pro.pk, pro.email, pro.username)
reset = User.objects.create_user(email=f'qa7e-reset-{ts}@example.invalid', username=f'qa7ereset{ts}', password=pw)
print('CREATED_USER', reset.pk, reset.email, reset.username)
plan = SubscriptionPlan.objects.get(name='Pro')          # the real row is only READ, never changed
now = timezone.now()
sub = UserSubscription.objects.create(
    user=pro, plan=plan, status=UserSubscription.SubscriptionStatus.ACTIVE,
    payment_method=UserSubscription.PaymentMethod.MANUAL,
    starts_at=now - timedelta(days=1), expires_at=now + timedelta(days=30),
)
print('CREATED_SUB', sub.pk, plan.name, plan.original_download)
