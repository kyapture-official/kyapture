"""
Chunk BILL-B: photo-storage estimate, Free collection cap, no per-collection
photo cap. Every limit is read from the plan table at request time, so an admin
edit changes the API and the enforcement with no restart.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.utils import get_user_subscription_metrics
from apps.galleries.models import Gallery
from apps.subscriptions import models as plan_models
from apps.subscriptions.entitlements import video_quota_violation
from apps.subscriptions.models import SubscriptionPlan, estimate_photo_count
from apps.subscriptions.seed import PLAN_SEED
from apps.subscriptions.testing import grant_plan

User = get_user_model()
PLANS = '/api/v1/subscriptions/plans/'
GALLERIES = '/api/v1/galleries/'


def make_user(name, **extra):
    return User.objects.create_user(
        email=f'{name}@kyapture.com', password='SecurePassword123!', username=name, **extra)


def make_collections(user, count, start=0):
    for i in range(start, start + count):
        Gallery.objects.create(photographer=user, title=f'Collection {i}', slug=f'collection-{i}')


class PhotoFieldRemovedTests(APITestCase):
    def test_field_is_gone_from_model_api_admin_and_metrics(self):
        self.assertNotIn('max_photos_per_gallery', [f.name for f in SubscriptionPlan._meta.get_fields()])
        for plan in self.client.get(PLANS).data:
            self.assertNotIn('max_photos_per_gallery', plan)
        model_admin = admin.site._registry[SubscriptionPlan]
        shown = [f for _title, opts in model_admin.fieldsets for f in opts['fields']]
        self.assertNotIn('max_photos_per_gallery', shown)
        self.assertNotIn('max_photos_per_gallery', get_user_subscription_metrics(make_user('someone')))

    def test_dashboard_stats_have_no_photo_limit(self):
        self.client.force_authenticate(user=make_user('stats'))
        self.assertNotIn('plan_photo_limit', self.client.get(f'{GALLERIES}dashboard/stats/').data)


class PhotoEstimateTests(APITestCase):
    def by_key(self):
        return {p['key']: p for p in self.client.get(PLANS).data}

    def test_three_gb_is_a_thousand_photos_computed_by_the_backend(self):
        free = self.by_key()['free']
        self.assertEqual(free['storage_gb'], 3)
        self.assertEqual(free['estimated_photos'], 1000)
        self.assertEqual(free['average_photo_size_mb'], plan_models.AVERAGE_PHOTO_SIZE_MB)
        self.assertEqual(plan_models.AVERAGE_PHOTO_SIZE_MB, 3)

    def test_rounds_down_to_two_significant_digits(self):
        self.assertEqual(
            [estimate_photo_count(gb) for gb in (1, 2, 3, 5, 20, 100, 500)],
            [330, 660, 1000, 1600, 6600, 33000, 160000])
        self.assertEqual({k: p['estimated_photos'] for k, p in self.by_key().items()},
                         {'free': 1000, 'basic': 6600, 'pro': 33000, 'studio': 160000})

    def test_changing_storage_in_the_table_changes_the_estimate(self):
        SubscriptionPlan.objects.filter(key='basic').update(storage_gb=30)
        self.assertEqual(self.by_key()['basic']['estimated_photos'], 10000)


class CollectionCapTests(APITestCase):
    def setUp(self):
        self.free = make_user('freeuser')
        self.client.force_authenticate(user=self.free)

    def create(self, title):
        return self.client.post(GALLERIES, {'title': title}, format='json')

    def test_eleventh_collection_on_free_is_refused_with_code_and_limit(self):
        make_collections(self.free, 10)
        response = self.create('Eleventh')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'gallery_limit_reached')
        self.assertEqual(response.data['plan_limit'], 10)
        self.assertEqual(response.data['plan_name'], 'Free')
        self.assertEqual(Gallery.objects.filter(photographer=self.free).count(), 10)   # nothing was created

    def test_tenth_collection_is_still_allowed(self):
        make_collections(self.free, 9)
        self.assertEqual(self.create('Tenth').status_code, status.HTTP_201_CREATED)

    def test_paid_plans_are_unlimited(self):
        for name in ('Basic', 'Pro', 'Studio'):
            user = make_user(name.lower() + 'user')
            grant_plan(user, name=name)
            self.client.force_authenticate(user=user)
            for i in range(12):
                Gallery.objects.create(photographer=user, title=f'{name} {i}', slug=f'{name.lower()}-{i}')
            response = self.client.post(GALLERIES, {'title': f'{name} extra'}, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, (name, response.data))

    def test_deleting_a_collection_frees_a_slot(self):
        make_collections(self.free, 10)
        self.assertEqual(self.create('Blocked').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f'{GALLERIES}collection-3/').status_code, status.HTTP_200_OK)
        self.assertEqual(self.create('Fits now').status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.create('Blocked again').status_code, status.HTTP_403_FORBIDDEN)

    def test_a_legacy_trashed_row_does_not_block_creation(self):
        make_collections(self.free, 10)
        Gallery.objects.filter(slug='collection-0').update(is_active=False)
        self.assertEqual(self.create('Live count only').status_code, status.HTTP_201_CREATED)

    def test_stats_report_live_usage_and_remaining_for_free(self):
        make_collections(self.free, 4)
        stats = self.client.get(f'{GALLERIES}dashboard/stats/').data
        self.assertEqual(
            (stats['galleries_used'], stats['plan_gallery_limit'], stats['galleries_remaining']), (4, 10, 6))


class AdminEditsApplyWithoutRestartTests(APITestCase):
    def setUp(self):
        self.free = make_user('freeuser')
        self.client.force_authenticate(user=self.free)

    def admin_save(self, plan, **changes):
        """A real submit of the Django admin change form (not an ORM shortcut)."""
        if not hasattr(self, 'admin_client'):
            self.admin_client = self.client_class()
            self.admin_client.force_login(make_user('boss', is_staff=True, is_superuser=True))
        data = {
            'name': plan.name, 'price': str(plan.price), 'is_active': 'on', 'storage_gb': plan.storage_gb,
            'max_collections': '' if plan.max_collections is None else plan.max_collections,
            'video_minutes': '' if plan.video_minutes is None else plan.video_minutes,
        }
        for flag in ('original_download', 'watermark', 'branding'):
            if getattr(plan, flag):
                data[flag] = 'on'
        data.update({k: '' if v is None else v for k, v in changes.items()})
        response = self.admin_client.post(f'/admin/subscriptions/subscriptionplan/{plan.pk}/change/', data)
        self.assertEqual(response.status_code, 302)

    def test_editing_max_collections_in_admin_changes_the_cap_and_the_api(self):
        free = SubscriptionPlan.get_free()
        make_collections(self.free, 10)
        self.assertEqual(
            self.client.post(GALLERIES, {'title': 'A'}, format='json').status_code, status.HTTP_403_FORBIDDEN)

        self.admin_save(free, max_collections=12)
        self.assertEqual({p['key']: p['max_collections'] for p in self.client.get(PLANS).data}['free'], 12)
        for title in ('B', 'C'):
            self.assertEqual(
                self.client.post(GALLERIES, {'title': title}, format='json').status_code, status.HTTP_201_CREATED)
        blocked = self.client.post(GALLERIES, {'title': 'D'}, format='json')
        self.assertEqual((blocked.status_code, blocked.data['plan_limit']), (status.HTTP_403_FORBIDDEN, 12))

        self.admin_save(SubscriptionPlan.get_free(), max_collections='')          # empty = unlimited
        self.assertEqual(
            self.client.post(GALLERIES, {'title': 'E'}, format='json').status_code, status.HTTP_201_CREATED)

    def test_capping_a_paid_plan_in_admin_applies_to_its_subscribers(self):
        pro = grant_plan(self.free, name='Pro')
        make_collections(self.free, 3)
        self.assertEqual(
            self.client.post(GALLERIES, {'title': 'Fine'}, format='json').status_code, status.HTTP_201_CREATED)
        self.admin_save(pro, max_collections=4)
        self.assertEqual(
            self.client.post(GALLERIES, {'title': 'Over'}, format='json').status_code, status.HTTP_403_FORBIDDEN)

    def test_editing_video_minutes_in_admin_changes_the_api_and_the_quota_rule(self):
        free = SubscriptionPlan.get_free()
        metrics = get_user_subscription_metrics(self.free)
        self.assertEqual(video_quota_violation(metrics, 60)['code'], 'video_not_in_plan')

        self.admin_save(free, video_minutes=5)
        self.assertEqual({p['key']: p['video_minutes'] for p in self.client.get(PLANS).data}['free'], 5)
        metrics = get_user_subscription_metrics(self.free)
        self.assertIsNone(video_quota_violation(metrics, 60))
        self.assertEqual(video_quota_violation(metrics, 600)['code'], 'video_minutes_exceeded')
        self.assertEqual(self.client.get(f'{GALLERIES}dashboard/stats/').data['video_minutes_limit'], 5)

        self.admin_save(SubscriptionPlan.get_free(), video_minutes='')           # empty = unlimited
        self.assertIsNone(video_quota_violation(get_user_subscription_metrics(self.free), 10 ** 6))


class NoHardCodedPlanValuesTests(APITestCase):
    def test_free_row_self_heals_from_the_seed_not_from_literals(self):
        SubscriptionPlan.objects.filter(key='free').delete()
        free = SubscriptionPlan.get_free()
        fields = ('storage_gb', 'max_collections', 'video_minutes', 'price')
        self.assertEqual(
            (free.storage_gb, free.max_collections, free.video_minutes, int(free.price)),
            tuple(PLAN_SEED['free'][k] for k in fields))

    def test_grant_plan_uses_the_plan_table_values(self):
        SubscriptionPlan.objects.filter(key='studio').update(storage_gb=777, max_collections=9, price=1234)
        plan = grant_plan(make_user('studiouser'), name='Studio')
        self.assertEqual((plan.storage_gb, plan.max_collections, int(plan.price)), (777, 9, 1234))
