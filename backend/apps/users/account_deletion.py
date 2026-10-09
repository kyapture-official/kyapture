# backend/apps/users/account_deletion.py
"""
Account deletion, no data export (chunk 7.5-E). Every rule lives here; the views (account_api.py) and the
Celery tasks (tasks.py) only call it.

The life of a deletion
----------------------
1. REQUEST  (request_deletion)  The owner re-enters the password (an account with no password types an emailed
   one-time code) and the account email. Under the user's row lock: staff are refused, a PENDING manual payment
   blocks the request (a payment under review is money in flight), then `deletion_requested_at` is stamped,
   every session ends (token_version, revoke_all_sessions), the public derivative keys rotate (the 7.5-A
   suspension door), an audit row is written and the "deletion requested" email (with the cancel link) is queued.
   From this moment the account is CLOSING: every public gallery lookup answers 404 (apps/users/ownership.py),
   a ZIP being built fails `owner_unavailable`, the daily billing job skips the account, and the API refuses
   every route except the cancel page (apps/core/authentication.py).
2. WAIT  Settings -> Account settings -> `deletion_cooling_off_days` (default 7). The owner can sign in, sees the
   "Cancel deletion" page, or uses the emailed link: cancel_deletion() clears the stamp and everything is back
   exactly as it was (nothing was deleted). With 0 days the purge is queued at once and cannot be cancelled.
3. PURGE  (purge_step, driven by the Celery task purge_account; the beat sweep starts due accounts and resumes
   stalled ones). Idempotent, resumable and batch-limited: each step does ONE bounded unit of work and the task
   repeats steps until none is left. FILES FIRST, THEN ROWS, through the 5.1-D purge path (apps/photos/purge.py):
   a failed file delete leaves the rows in place and the task retries, so a row never disappears before its file.
   Order: a batch of photos/videos (their originals, masters, derivatives, cached Web Sizes) -> a whole empty
   collection (its key prefix in both storages and its prepared ZIPs) -> the account's own files (avatar, logo,
   payment proofs) -> ONE final transaction that re-checks the status under the row lock, anonymises the
   approved payments, cancels the subscription, deletes the account (its notifications, feedback, reset links and
   everything else cascade) and writes the audit row. The "account deleted" email is queued once, by that
   transaction, after it commits.

Races: the purge's first step and the request/cancel both take the user's row lock (FOR NO KEY UPDATE) and
re-read the status inside it, so a cancel and a purge start cannot both win; uploads and manual-payment
submissions take the same lock and refuse a closing account, so no new data is created once the stamp is set.
"""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.core.emailing import app_url, format_date, safe_send_email, send_email

from . import audit
from .models import AccountSettings, User

logger = logging.getLogger(__name__)

Action = audit.Action

# Coarse reasons for the audit rows (never free text, never a name or an address).
REASON_REQUESTED = 'requested'
REASON_REQUESTED_NOW = 'requested_now'      # cooling-off of 0 days: the purge was queued at once
REASON_CANCELLED = 'cancelled'
REASON_CANCELLED_LINK = 'cancelled_by_link'
REASON_COMPLETED = 'completed'

TOKEN_BYTES = 32
TOKEN_MAX_LENGTH = 128
LOCK_SECONDS = 15 * 60       # one purge runner per account at a time
ALIVE_SECONDS = 30 * 60      # the beat sweep leaves an account alone while a runner touched it this recently
MAX_STEPS_PER_RUN = 25       # steps one task invocation may do before it re-queues itself


class DeletionError(Exception):
    """A refusal with a stable `code` (the client branches on it) and a message safe to show."""

    def __init__(self, code, message, http_status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ─── small helpers ───────────────────────────────────────────────────────────

def hash_token(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def payer_hash(email):
    """HMAC of the lower-cased address: lets two payments of one person still be matched, reveals nothing alone."""
    return salted_hmac('kyapture.account-deletion.payer', (email or '').strip().lower(), algorithm='sha256').hexdigest()


def cancel_link(raw):
    """In the fragment, like the reset link (7-C): a browser never sends it to any server."""
    return app_url(f'/cancel-deletion#token={raw}')


def is_closing(user):
    return user.deletion_requested_at is not None


def state_of(user):
    if user.deletion_requested_at is None:
        return 'none'
    return 'purging' if user.deletion_started_at is not None else 'pending'


def blockers(user):
    """Reasons the account cannot be deleted right now, as stable codes."""
    from apps.subscriptions.models import ManualPayment

    found = []
    if user.is_staff or user.is_superuser:
        found.append('staff')
    if ManualPayment.objects.filter(user=user, status=ManualPayment.VerificationStatus.PENDING).exists():
        found.append('payment_pending')
    return found


BLOCKER_MESSAGES = {
    'staff': ('staff_cannot_delete', 'Staff accounts cannot be deleted here. Ask another administrator.', 403),
    'payment_pending': (
        'payment_pending',
        'A payment you sent is still waiting for review. Wait for the decision (or until it is rejected), then delete the account.',
        409,
    ),
}


def status_payload(user):
    """What the Settings page and the pending page need. No secret, no other account's data."""
    return {
        'state': state_of(user),
        'requested_at': user.deletion_requested_at,
        'scheduled_for': user.deletion_scheduled_for,
        'cooling_off_days': AccountSettings.load().deletion_cooling_off_days,
        'uses_password': user.has_usable_password(),
        'is_staff': bool(user.is_staff or user.is_superuser),
        'blockers': blockers(user),
    }


def _refuse_blockers(user):
    for code in blockers(user):
        raise DeletionError(*BLOCKER_MESSAGES[code])


# ─── the one-time code (accounts with no password) ───────────────────────────

def _code_keys(user):
    return f'acctdel:code:{user.pk}', f'acctdel:tries:{user.pk}'


def _code_digest(user, code):
    return salted_hmac('kyapture.account-deletion.code', f'{user.pk}:{code}', algorithm='sha256').hexdigest()


def send_confirmation_code(user):
    """Emails a 6-digit code (stored hashed in the shared cache, ten minutes, a few tries). Only for an account with no password."""
    if user.has_usable_password():
        raise DeletionError('password_account', 'This account confirms with its password.', 400)
    code_key, tries_key = _code_keys(user)
    code = f'{secrets.randbelow(10 ** 6):06d}'
    ttl = settings.ACCOUNT_DELETION_CODE_MINUTES * 60
    cache.set(code_key, _code_digest(user, code), timeout=ttl)
    cache.delete(tries_key)
    # In the request on purpose, like the download code (7-B): a secret should not travel through the broker.
    if not safe_send_email('deletion_code', user.email, {'code': code, 'minutes': settings.ACCOUNT_DELETION_CODE_MINUTES}):
        cache.delete(code_key)
        raise DeletionError('email_failed', 'We could not send the code. Try again in a moment.', 503)


def _check_code(user, code):
    code_key, tries_key = _code_keys(user)
    wrong = DeletionError('code_invalid', 'That code is wrong or has expired. Ask for a new one.', 400)
    stored = cache.get(code_key)
    if not stored or not isinstance(code, str) or not code.strip():
        raise wrong
    cache.add(tries_key, 0, timeout=settings.ACCOUNT_DELETION_CODE_MINUTES * 60)
    try:
        tries = cache.incr(tries_key)
    except ValueError:
        raise wrong
    if tries > settings.ACCOUNT_DELETION_CODE_MAX_TRIES:
        cache.delete(code_key)
        raise wrong
    if not constant_time_compare(stored, _code_digest(user, code.strip())):
        raise wrong
    cache.delete_many([code_key, tries_key])


# ─── 1. request ──────────────────────────────────────────────────────────────

def request_deletion(user, *, password='', code='', typed_email=''):
    """
    Starts a deletion for `user` after the confirmations. Returns the new status payload. Raises DeletionError.
    The sessions of the account end here, this request's included (the view clears the cookies).
    """
    from .tasks import purge_account, send_deletion_requested_email

    _refuse_blockers(user)
    if is_closing(user):
        raise DeletionError('already_pending', 'This account is already scheduled for deletion.', 409)
    if not isinstance(typed_email, str) or typed_email.strip().lower() != (user.email or '').lower():
        raise DeletionError('email_mismatch', 'Type your account email exactly as shown.', 400)
    if user.has_usable_password():
        if not isinstance(password, str) or not password:
            raise DeletionError('password_required', 'Enter your password.', 400)
        if not user.check_password(password):
            raise DeletionError('password_wrong', 'That password is not correct.', 400)
    else:
        _check_code(user, code)

    from .utils import revoke_all_sessions
    from .staff_api import close_public_media

    with transaction.atomic():
        locked = User.objects.select_for_update(no_key=True).get(pk=user.pk)
        _refuse_blockers(locked)               # again, under the lock: a payment submit takes the same lock
        if is_closing(locked):
            raise DeletionError('already_pending', 'This account is already scheduled for deletion.', 409)
        days = AccountSettings.load().deletion_cooling_off_days
        now = timezone.now()
        locked.deletion_requested_at = now
        locked.deletion_scheduled_for = now + timedelta(days=days)
        locked.save(update_fields=['deletion_requested_at', 'deletion_scheduled_for'])
        revoke_all_sessions(locked)            # logged out everywhere, at once
        if days:
            close_public_media(locked)         # the 7.5-A door: new random keys for the public derivatives
        audit.record_account_event(
            Action.ACCOUNT_DELETION_REQUESTED, locked.pk, locked.email,
            reason=REASON_REQUESTED if days else REASON_REQUESTED_NOW,
        )
        user_id = str(locked.pk)

        def dispatch():
            try:
                if days:
                    send_deletion_requested_email.delay(user_id)
                else:
                    purge_account.delay(user_id)
            except Exception:
                logger.exception('Could not queue the deletion task for user_id=%s', user_id)

        transaction.on_commit(dispatch)
    return status_payload(locked)


# ─── 2. cancel ───────────────────────────────────────────────────────────────

def cancel_deletion(*, user=None, token=None):
    """
    Cancels a waiting deletion, by the signed-in owner (`user`) or by the emailed link's `token`. Under the row
    lock, with the status re-read inside it: once the purge has started there is no way back (409).
    """
    if user is None:
        if not isinstance(token, str) or not token or len(token) > TOKEN_MAX_LENGTH:
            raise DeletionError('cancel_link_invalid', 'This link is not valid. Sign in to cancel the deletion.', 400)
    with transaction.atomic():
        rows = User.objects.select_for_update(no_key=True)
        if user is not None:
            locked = rows.filter(pk=user.pk).first()
        else:
            locked = rows.filter(deletion_cancel_hash=hash_token(token)).first()
        if locked is None or locked.deletion_requested_at is None:
            if user is None:
                raise DeletionError('cancel_link_invalid', 'This link is not valid. Sign in to cancel the deletion.', 400)
            raise DeletionError('not_pending', 'This account is not scheduled for deletion.', 409)
        if locked.deletion_started_at is not None:
            raise DeletionError('purge_started', 'It is too late: the deletion has already started.', 409)
        locked.deletion_requested_at = None
        locked.deletion_scheduled_for = None
        locked.deletion_cancel_hash = None
        locked.save(update_fields=['deletion_requested_at', 'deletion_scheduled_for', 'deletion_cancel_hash'])
        audit.record_account_event(
            Action.ACCOUNT_DELETION_CANCELLED, locked.pk, locked.email,
            reason=REASON_CANCELLED if user is not None else REASON_CANCELLED_LINK,
        )
    return status_payload(locked)


# ─── emails (task bodies) ────────────────────────────────────────────────────

def send_requested_email(user_id):
    """
    Task body: a fresh cancel link and the "deletion requested" email. The token is made HERE (never passed
    through the broker); only its hash is stored, and a retry replaces it (only the newest link works).
    """
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    with transaction.atomic():
        user = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
        if user is None or user.deletion_requested_at is None or user.deletion_started_at is not None:
            return False                       # cancelled, purging or gone: no link to send
        user.deletion_cancel_hash = hash_token(raw)
        user.save(update_fields=['deletion_cancel_hash'])
        context = {
            'display_name': user.display_name or user.username,
            'email': user.email,
            'scheduled_date': format_date(user.deletion_scheduled_for),
            'days': AccountSettings.load().deletion_cooling_off_days,
            'cancel_url': cancel_link(raw),
        }
        to = user.email
    send_email('deletion_requested', to, context)
    logger.info('Deletion requested email sent for user_id=%s', user_id)
    return True


def send_deleted_email(email):
    """Task body: the one "account deleted" notice to the old address."""
    send_email('account_deleted', email, {'email': email})
    logger.info('Account deleted email sent')
    return True


# ─── payments: anonymised, never deleted (approved ones) ─────────────────────

def anonymise_payments(user, *, schedule_file_purge=False):
    """
    Approved payments are financial records and stay: the user link is removed, the address is replaced by an
    HMAC, the amount, dates, plan and reference stay, and the typed note and the proof file go. Every other
    payment (rejected, or pending if one slipped in) is deleted with its proof. Returns the proof file refs.
    Idempotent: a second call finds no payment of this user.
    """
    from apps.subscriptions.models import ManualPayment

    payments = list(ManualPayment.objects.filter(user=user))
    if not payments:
        return []
    refs = [{'s': 'private', 'n': p.payment_proof.name} for p in payments if p.payment_proof]
    approved = [p.pk for p in payments if p.status == ManualPayment.VerificationStatus.APPROVED]
    ManualPayment.objects.filter(pk__in=approved).update(
        user=None, payer_hash=payer_hash(user.email), notes='', payment_proof='', proof_type='', proof_size=0,
    )
    ManualPayment.objects.filter(user=user).delete()
    if schedule_file_purge and refs:
        from apps.photos.purge import schedule_purge
        schedule_purge(refs)
    return refs


# ─── 3. purge ────────────────────────────────────────────────────────────────

def _begin(user_id):
    """
    The status check that starts (or resumes) a purge, under the row lock. Returns (user, outcome):
    outcome 'go' to continue; 'gone', 'noop' (never requested, or cancelled) or 'not_due' to stop.
    """
    now = timezone.now()
    with transaction.atomic():
        user = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
        if user is None:
            return None, 'gone'
        if user.deletion_requested_at is None:
            return None, 'noop'
        if user.deletion_started_at is None:
            if user.deletion_scheduled_for is None or user.deletion_scheduled_for > now:
                return None, 'not_due'
            if user.is_staff or user.is_superuser:      # promoted after the request: never purge a staff account
                logger.error('Refusing to purge staff account user_id=%s', user_id)
                User.objects.filter(pk=user.pk).update(
                    deletion_requested_at=None, deletion_scheduled_for=None, deletion_cancel_hash=None)
                return None, 'noop'
            from .utils import revoke_all_sessions
            user.deletion_started_at = now
            user.deletion_cancel_hash = None            # the cancel link dies with the start
            user.is_active = False                      # no sign-in, no token, no public gallery from here on
            user.save(update_fields=['deletion_started_at', 'deletion_cancel_hash', 'is_active'])
            revoke_all_sessions(user)
        return user, 'go'


def _purge_assets_batch(user):
    """Files of up to ACCOUNT_PURGE_BATCH_ASSETS photos/videos, then their rows. 'empty' | 'more' | 'retry'."""
    from apps.photos.models import MediaAsset
    from apps.photos.purge import PRIVATE, asset_refs, discarding_purges, run_purge, web_size_prefix

    assets = list(
        MediaAsset.objects.filter(gallery__photographer_id=user.pk).order_by('pk')[:settings.ACCOUNT_PURGE_BATCH_ASSETS]
    )
    if not assets:
        return 'empty'
    refs, prefixes = [], []
    for asset in assets:
        refs.extend(asset_refs(asset))
        cache_prefix = web_size_prefix(asset)
        if cache_prefix:
            prefixes.append({'s': PRIVATE, 'n': cache_prefix})
    failed_refs, failed_prefixes = run_purge(refs, prefixes)
    if failed_refs or failed_prefixes:
        logger.error('Account purge: %s file(s) could not be deleted for user_id=%s; rows kept, will retry',
                     len(failed_refs) + len(failed_prefixes), user.pk)
        return 'retry'
    with transaction.atomic(), discarding_purges():
        MediaAsset.objects.filter(pk__in=[a.pk for a in assets], gallery__photographer_id=user.pk).delete()
    return 'more'


def _purge_next_gallery(user):
    """A collection that holds no photo any more: its key prefixes and prepared ZIPs, then its row. 'none' | 'more' | 'retry'."""
    from apps.clients.download_jobs import STORAGE_PREFIX, job_storage_refs
    from apps.clients.models import DownloadJob
    from apps.galleries.models import Gallery
    from apps.photos.models import MediaAsset
    from apps.photos.purge import PRIVATE, PUBLIC, discarding_purges, gallery_prefix, run_purge

    gallery = Gallery.objects.filter(photographer_id=user.pk).order_by('pk').first()
    if gallery is None:
        return 'none'
    jobs = list(DownloadJob.objects.filter(gallery=gallery))
    refs = job_storage_refs(jobs)
    prefixes = [{'s': PRIVATE, 'n': gallery_prefix(gallery)}, {'s': PUBLIC, 'n': gallery_prefix(gallery)}]
    prefixes += [{'s': PRIVATE, 'n': f'{STORAGE_PREFIX}/{job.id}/'} for job in jobs]
    failed_refs, failed_prefixes = run_purge(refs, prefixes)
    if failed_refs or failed_prefixes:
        logger.error('Account purge: collection files could not be deleted for user_id=%s; rows kept, will retry', user.pk)
        return 'retry'
    with transaction.atomic(), discarding_purges():
        locked = Gallery.objects.select_for_update(no_key=True).filter(pk=gallery.pk).first()
        if locked is not None:
            if MediaAsset.objects.filter(gallery=locked).exists():
                return 'more'                  # an upload landed in the meantime: the next step purges it first
            locked.delete()
    return 'more'


def _finish(user):
    """The account's own files, then ONE transaction that removes the account. 'done' | 'more' | 'retry' | 'gone' | 'noop'."""
    from apps.galleries.models import Gallery
    from apps.photos.purge import PRIVATE, PUBLIC, run_purge
    from apps.subscriptions.models import ManualPayment, UserSubscription

    proofs = [
        {'s': PRIVATE, 'n': name}
        for name in ManualPayment.objects.filter(user=user).exclude(payment_proof='').values_list('payment_proof', flat=True)
    ]
    prefixes = [
        {'s': PRIVATE, 'n': f'photographers/{user.pk}/'},      # originals tree, Web Sizes, avatar, logo
        {'s': PUBLIC, 'n': f'photographers/{user.pk}/'},       # public derivatives, avatar, logo
        {'s': PRIVATE, 'n': f'payment_proofs/{user.pk}/'},
    ]
    failed_refs, failed_prefixes = run_purge(proofs, prefixes)
    if failed_refs or failed_prefixes:
        logger.error('Account purge: the account files could not be deleted for user_id=%s; rows kept, will retry', user.pk)
        return 'retry'

    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    with transaction.atomic():
        locked = User.objects.select_for_update(no_key=True).filter(pk=user.pk).first()
        if locked is None:
            return 'gone'
        if locked.deletion_requested_at is None or locked.deletion_started_at is None:
            return 'noop'                      # the status is re-checked under the lock
        if Gallery.objects.filter(photographer=locked).exists():
            return 'more'
        email = locked.email
        anonymise_payments(locked)             # proof files were deleted above
        OutstandingToken.objects.filter(user=locked).delete()
        for subscription in UserSubscription.objects.select_for_update().filter(user=locked):
            subscription.status = UserSubscription.SubscriptionStatus.CANCELLED      # cancelled, then removed with the account
            subscription.save(update_fields=['status', 'updated_at'])
        audit.record_account_event(Action.ACCOUNT_DELETION_COMPLETED, locked.pk, email, reason=REASON_COMPLETED)
        locked.delete()                        # notifications, feedback, reset links, subscription: cascade

        def farewell():
            from .tasks import send_account_deleted_email
            try:
                send_account_deleted_email.delay(email)
            except Exception:
                logger.exception('Could not queue the account deleted email')

        transaction.on_commit(farewell)
    return 'done'


def purge_step(user_id):
    """
    ONE bounded unit of purge work. Returns 'more' (call again), 'retry' (a file delete failed: rows were kept),
    'done', or a stop word ('gone', 'noop', 'not_due'). Safe to call any number of times, from any process.
    """
    user, outcome = _begin(user_id)
    if user is None:
        return outcome
    for stage in (_purge_assets_batch, _purge_next_gallery):
        result = stage(user)
        if result not in ('empty', 'none'):
            return result
    return _finish(user)


def run_purge_steps(user_id, max_steps=MAX_STEPS_PER_RUN):
    """
    Runs steps until the account is gone, a step needs a retry, or `max_steps` were done. One runner per account
    (a cache lock); an account touched in the last half hour is skipped by the beat sweep.
    """
    lock_key, alive_key = f'acctdel:lock:{user_id}', f'acctdel:alive:{user_id}'
    if not cache.add(lock_key, 1, timeout=LOCK_SECONDS):
        return 'busy'
    try:
        cache.set(alive_key, 1, timeout=ALIVE_SECONDS)
        for _ in range(max_steps):
            outcome = purge_step(user_id)
            if outcome != 'more':
                return outcome
        return 'more'
    finally:
        cache.delete(lock_key)


def sweep_due(limit=100):
    """
    Queues a purge for every account whose cooling-off has ended and for every purge that stopped half way
    (no runner touched it for half an hour). Returns how many were queued.
    """
    from .tasks import purge_account

    now = timezone.now()
    ids = list(
        User.objects.filter(deletion_requested_at__isnull=False)
        .filter(Q(deletion_started_at__isnull=False) | Q(deletion_scheduled_for__lte=now))
        .order_by('deletion_requested_at').values_list('pk', flat=True)[:limit]
    )
    queued = 0
    for pk in ids:
        if cache.get(f'acctdel:alive:{pk}'):
            continue
        purge_account.delay(str(pk))
        queued += 1
    return queued
