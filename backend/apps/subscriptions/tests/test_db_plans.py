"""
DB-backed plans (chunk BILL-A): the plan table is the single source of truth.
Prices, limits and feature flags are read from SubscriptionPlan at request
time, so an admin edit changes the API, the Billing page and entitlement
enforcement immediately — no restart, no deploy.
"""
import io
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.galleries.models import Gallery
from apps.subscriptions.entitlements import get_feature_entitlements, upgrade_message
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.testing import grant_plan

User = get_user_model()
PLANS = '/api/v1/subscriptions/plans/'


def make_user(name, **extra):
    return User.objects.create_user(
        email=f'{name}@kyapture.com', password='SecurePassword123!', username=name,
        display_name=name.title(), **extra)


class PlansApiTests(APITestCase):
    def by_key(self):
        response = self.client.get(PLANS)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {plan['key']: plan for plan in response.data}

    def test_plans_api_returns_the_seeded_db_values(self):
        plans = self.by_key()
        self.assertEqual(list(plans), ['free', 'basic', 'pro', 'studio'])      # ordered by price
        for key, price, gb in (('free', 0, 3), ('basic', 499, 20), ('pro', 1499, 100), ('studio', 2999, 500)):
            self.assertEqual(Decimal(plans[key]['price']), price, key)
            self.assertEqual(plans[key]['storage_gb'], gb, key)
            self.assertIsNone(plans[key]['max_collections'], key)              # unlimited everywhere
            self.assertIsNone(plans[key]['video_minutes'], key)
        self.assertTrue(plans['free']['is_free'])
        flags = {k: {f['key']: f['included'] for f in p['features']} for k, p in plans.items()}
        self.assertEqual(flags['pro'], {'branding': True, 'watermark': True, 'original_download': True})
        self.assertEqual(flags['basic'], {'branding': False, 'watermark': False, 'original_download': False})

    def test_changing_a_price_in_the_table_changes_the_api_immediately(self):
        self.assertEqual(Decimal(self.by_key()['basic']['price']), 499)
        SubscriptionPlan.objects.filter(key='basic').update(price=Decimal('650.00'), storage_gb=40)
        basic = self.by_key()['basic']
        self.assertEqual(Decimal(basic['price']), 650)
        self.assertEqual(basic['storage_gb'], 40)

    def test_inactive_plans_are_hidden_and_new_plans_appear(self):
        SubscriptionPlan.objects.filter(key='studio').update(is_active=False)
        SubscriptionPlan.objects.create(name='Agency', price=5000, storage_gb=1000, watermark=True)
        keys = list(self.by_key())
        self.assertNotIn('studio', keys)
        self.assertEqual(keys[-1], 'agency')                                   # key derived from name
        agency = self.by_key()['agency']
        self.assertEqual(
            {f['key']: f['included'] for f in agency['features']},
            {'branding': False, 'watermark': True, 'original_download': False})

    def test_free_plan_row_cannot_be_deleted_in_admin(self):
        model_admin = admin.site._registry[SubscriptionPlan]

        class Request:
            user = make_user('boss', is_staff=True, is_superuser=True)
        self.assertFalse(model_admin.has_delete_permission(Request, SubscriptionPlan.get_free()))
        self.assertTrue(model_admin.has_delete_permission(Request, SubscriptionPlan.objects.get(key='basic')))


class EntitlementsUseThePlanTableTests(APITestCase):
    def setUp(self):
        self.free = make_user('freeuser')
        self.pro = make_user('prouser')
        grant_plan(self.pro)

    def test_toggling_a_flag_on_the_plan_row_changes_entitlement_for_its_subscribers(self):
        self.assertTrue(get_feature_entitlements(self.pro)['watermark'])
        SubscriptionPlan.objects.filter(name='Pro').update(watermark=False)
        result = get_feature_entitlements(self.pro)
        self.assertFalse(result['watermark'])
        self.assertTrue(result['branding'])                                    # flags are independent

    def test_free_row_flags_apply_to_unpaid_users(self):
        self.assertFalse(get_feature_entitlements(self.free)['original_download'])
        SubscriptionPlan.objects.filter(key='free').update(original_download=True)
        self.assertTrue(get_feature_entitlements(self.free)['original_download'])

    def test_my_subscription_endpoint_uses_the_same_flags(self):
        self.client.force_authenticate(user=self.free)
        data = self.client.get('/api/v1/subscriptions/my-subscription/').data
        self.assertFalse(data['entitlements']['branding'])
        SubscriptionPlan.objects.filter(key='free').update(branding=True)
        self.assertTrue(self.client.get('/api/v1/subscriptions/my-subscription/').data['entitlements']['branding'])

    def test_upgrade_copy_names_the_cheapest_plan_that_has_the_feature(self):
        self.assertIn('Pro plan and above', upgrade_message('watermark'))
        SubscriptionPlan.objects.filter(key='basic').update(watermark=True)
        self.assertIn('Basic plan and above', upgrade_message('watermark'))
        SubscriptionPlan.objects.update(watermark=False)
        self.assertIn('paid plan', upgrade_message('watermark'))


class FreeUserCannotUseProFeaturesDirectlyTests(APITestCase):
    """Backend is authoritative: direct API calls bypass the UI entirely."""

    def setUp(self):
        self.free = make_user('freeuser')
        self.gallery = Gallery.objects.create(
            photographer=self.free, title='G', slug='g', is_published=True, is_active=True)
        self.client.force_authenticate(user=self.free)

    def patch(self, payload):
        return self.client.patch(f'/api/v1/galleries/{self.gallery.slug}/', payload, format='json')

    def test_watermark_is_refused(self):
        response = self.patch({'watermark_enabled': True})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'watermark_requires_upgrade')
        self.assertIn('Pro plan and above', response.data['error'])            # copy comes from the table

    def test_original_download_is_refused(self):
        response = self.patch({'design_settings': {'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}}})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'original_download_requires_upgrade')

    def test_branding_logo_upload_is_refused(self):
        buf = io.BytesIO()
        Image.new('RGB', (40, 40), (10, 120, 60)).save(buf, format='PNG')
        logo = SimpleUploadedFile('logo.png', buf.getvalue(), content_type='image/png')
        response = self.client.put('/api/v1/auth/me/', {'logo': logo}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'branding_requires_upgrade')

    def test_free_plan_cannot_be_purchased_via_manual_payment(self):
        free = SubscriptionPlan.get_free()
        response = self.client.post(
            '/api/v1/subscriptions/payments/', {'plan': str(free.id), 'amount': '0'}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('plan', response.data)

    def test_admin_enabling_the_feature_on_free_row_unlocks_it(self):
        SubscriptionPlan.objects.filter(key='free').update(watermark=True)
        self.assertNotEqual(self.patch({'watermark_enabled': True}).status_code, status.HTTP_403_FORBIDDEN)
