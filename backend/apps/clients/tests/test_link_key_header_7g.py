# backend/apps/clients/tests/test_link_key_header_7g.py
"""
7G (reviewer 7R-2, R3): the prepared download's 7-day job key travels in the
X-Download-Link-Key request header, never in the query string (a query string
is written to every access log; the dev log held 13 full keys).

  - the header opens the job's status, as `?link_token=` did;
  - `?link_token=` is refused (400 link_key_in_query), even with a valid key,
    unless the transition flag DOWNLOAD_LINK_KEY_QUERY_FALLBACK is on;
  - a cross-origin preflight allows the header (the app calls the API from
    another origin).
The access log itself is checked in the browser QA (docs/qa-7g/results.md).
"""
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status

from apps.clients.tests.test_download_pages_1r5b import JobBase


class LinkKeyHeaderTests(JobBase):
    def status_url(self, job):
        return f'{self.base}download-jobs/{job.id}/'

    def test_the_header_opens_the_job(self):
        job, response = self.prepare_job()
        cache.clear()
        ready = self.client.get(self.status_url(job), HTTP_X_DOWNLOAD_LINK_KEY=response.data['link_token'])
        self.assertEqual(ready.status_code, status.HTTP_200_OK, ready.data)
        self.assertEqual(ready.data['state'], 'ready')
        self.assertTrue(ready.data['files'][0]['url'])

    def test_a_key_in_the_query_string_is_refused_even_when_valid(self):
        job, response = self.prepare_job()
        refused = self.client.get(self.status_url(job), {'link_token': response.data['link_token']})
        self.assertEqual((refused.status_code, refused.data['code']), (400, 'link_key_in_query'))
        self.assertNotIn('files', refused.data)

    def test_a_key_in_the_query_string_is_refused_next_to_a_valid_header(self):
        job, response = self.prepare_job()
        key = response.data['link_token']
        refused = self.client.get(self.status_url(job), {'link_token': key}, HTTP_X_DOWNLOAD_LINK_KEY=key)
        self.assertEqual(refused.status_code, 400)

    @override_settings(DOWNLOAD_LINK_KEY_QUERY_FALLBACK=True)
    def test_the_transition_flag_still_reads_a_query_key(self):
        job, response = self.prepare_job()
        ready = self.client.get(self.status_url(job), {'link_token': response.data['link_token']})
        self.assertEqual(ready.status_code, status.HTTP_200_OK, ready.data)

    def test_a_forged_header_reads_as_not_found(self):
        job, _ = self.prepare_job()
        denied = self.client.get(self.status_url(job), HTTP_X_DOWNLOAD_LINK_KEY='garbage')
        self.assertEqual((denied.status_code, denied.data['code']), (404, 'download_not_found'))

    @override_settings(CORS_ALLOWED_ORIGINS=['http://localhost:3000'])
    def test_a_cross_origin_preflight_allows_the_header(self):
        job, _ = self.prepare_job()
        preflight = self.client.options(
            self.status_url(job), HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='x-download-link-key',
        )
        self.assertEqual(preflight.status_code, 200)
        allowed = [h.strip().lower() for h in preflight['Access-Control-Allow-Headers'].split(',')]
        self.assertIn('x-download-link-key', allowed)
