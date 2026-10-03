# backend/apps/clients/tests/zip_flow.py
"""
Test helpers for the prepared (background) gallery/set download flow:

    POST .../download-access/        -> download_token       (email / PIN gate)
    POST .../download/               -> 202 {job_id}         (creates the job)
    GET  .../download-jobs/{id}/     -> {state, files[url]}  (poll)
    GET  <file url>                  -> the ZIP attachment

`request_zip()` walks that whole path and hands back the FINAL file response
(or the first non-success response), so a test can assert on whichever stage it
is about: error codes from the gates come back unchanged, and a successful
call returns the streaming ZIP response with its Content-Disposition.

InlineDownloadJobsMixin runs the Celery task inline (no broker/worker needed,
independent of CELERY_TASK_ALWAYS_EAGER) and removes the ZIPs it stored.
"""
import os
from unittest import mock

from apps.clients.download_jobs import run_download_job
from apps.core.storage import PrivateMediaStorage


def _job_dirs():
    try:
        return set(PrivateMediaStorage().listdir('download_jobs')[0])
    except (FileNotFoundError, NotImplementedError):
        return set()


class InlineDownloadJobsMixin:
    """Runs prepare jobs inline and deletes every ZIP the class stored."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        existing_dirs = _job_dirs()

        def run_inline(job_id):
            return run_download_job(job_id)

        patcher = mock.patch('apps.clients.views.prepare_download_job.delay', side_effect=run_inline)
        patcher.start()
        cls.addClassCleanup(patcher.stop)

        def remove_files():
            # Jobs may also be run directly by a test; anything new under
            # download_jobs/ was created by this class.
            storage = PrivateMediaStorage()
            for directory in _job_dirs() - existing_dirs:
                try:
                    for name in storage.listdir(f'download_jobs/{directory}')[1]:
                        storage.delete(f'download_jobs/{directory}/{name}')
                    os.rmdir(storage.path(f'download_jobs/{directory}'))
                except OSError:
                    pass

        cls.addClassCleanup(remove_files)


def follow_prepared(client, base, prepared, *, download_token=None, unlock_token=None):
    """Poll a 202 prepare response and fetch its first file; pass anything else through."""
    if prepared.status_code != 202:
        return prepared
    params = {}
    if download_token:
        params['download_token'] = download_token
    if unlock_token:
        params['token'] = unlock_token
    status_response = client.get(f"{base}download-jobs/{prepared.data['job_id']}/", params)
    if status_response.status_code != 200 or status_response.data.get('state') != 'ready':
        return status_response
    url = status_response.data['files'][0]['url']
    if unlock_token:
        url = f"{url}&token={unlock_token}"
    return client.get(url)


def request_zip(client, base, payload=None, *, unlock_token=None):
    """
    Authorize (email / pin in `payload` go to download-access), prepare, poll and
    fetch. Remaining payload keys (resolution, set_id, asset_ids, ...) go to the
    prepare POST. A ready-made `download_token` in the payload skips the grant.
    """
    payload = dict(payload or {})
    email = payload.pop('email', None)
    pin = payload.pop('pin', None)
    download_token = payload.pop('download_token', None)

    if download_token is None and (email is not None or pin is not None):
        grant_body = {key: value for key, value in (('email', email), ('pin', pin)) if value is not None}
        headers = {'HTTP_AUTHORIZATION': f'Bearer {unlock_token}'} if unlock_token else {}
        access = client.post(f"{base}download-access/", grant_body, format='json', **headers)
        if access.status_code != 200:
            return access
        download_token = access.data['download_token']

    if download_token:
        payload['download_token'] = download_token
    if unlock_token:
        payload['token'] = unlock_token
    prepared = client.post(f"{base}download/", payload, format='json')
    return follow_prepared(client, base, prepared, download_token=download_token, unlock_token=unlock_token)
