# backend/apps/galleries/tests/test_admin_design_settings_7g.py
"""
7G (reviewer 7R-2, R4): saving a gallery in the Django admin must not write
back design_settings as they were when the form was opened. A PIN use (the
"Limit PIN Usage" counter, design_settings.privacy.pin_use_count) or an owner
change made meanwhile must survive the admin save. design_settings is
read-only in the admin, and the admin saves only the fields its form edits.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.clients.download_access import record_pin_use
from apps.galleries.models import Gallery

User = get_user_model()


def submitted(form):
    """The POST body a browser sends for an unchanged admin change form."""
    data = {}
    for name, field in form.fields.items():
        value = form[name].value()
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = 'on'
        elif isinstance(field, forms.SplitDateTimeField):
            value = field.widget.decompress(value) if value else ['', '']
            data[f'{name}_0'], data[f'{name}_1'] = [v if v is not None else '' for v in value]
        elif value is not None:                 # BoundField.value() is already prepared for the widget
            data[name] = value
    return data


class AdminDesignSettingsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(email='admin7g@kyapture.com', password='SecurePassword123!',
                                                   username='admin7g')
        self.owner = User.objects.create_user(email='owner7g@kyapture.com', password='SecurePassword123!',
                                              username='owner7g')
        self.gallery = Gallery.objects.create(
            photographer=self.owner, title='Admin 7G', slug='admin-7g', is_published=True, is_active=True,
            allow_download=True, download_pin_hash='$2b$04$' + 'x' * 53,
            design_settings={'privacy': {'pin_limit': 5, 'pin_use_count': 1}, 'downloads': {'require_email': True}},
        )
        self.client.force_login(self.staff)
        self.url = f'/admin/galleries/gallery/{self.gallery.pk}/change/'

    def stored(self):
        return Gallery.objects.get(pk=self.gallery.pk)

    def test_a_pin_use_between_opening_and_saving_the_admin_form_survives(self):
        opened = self.client.get(self.url)
        self.assertEqual(opened.status_code, 200)
        body = submitted(opened.context['adminform'].form)
        body['title'] = 'Renamed by staff'

        self.assertIsNone(record_pin_use(self.stored()))          # a visitor uses the PIN meanwhile
        self.assertEqual(self.stored().design_settings['privacy']['pin_use_count'], 2)

        saved = self.client.post(self.url, {**body, '_save': 'Save'})
        self.assertEqual(saved.status_code, 302, getattr(saved, 'context', None) and
                         saved.context['adminform'].form.errors)
        after = self.stored()
        self.assertEqual(after.title, 'Renamed by staff')
        self.assertEqual(after.design_settings['privacy']['pin_use_count'], 2, after.design_settings)

    def test_design_settings_cannot_be_posted_through_the_admin(self):
        opened = self.client.get(self.url)
        body = submitted(opened.context['adminform'].form)
        body['design_settings'] = '{"privacy": {"pin_limit": 5, "pin_use_count": 0}}'
        self.assertEqual(self.client.post(self.url, {**body, '_save': 'Save'}).status_code, 302)
        self.assertEqual(self.stored().design_settings['privacy']['pin_use_count'], 1)
