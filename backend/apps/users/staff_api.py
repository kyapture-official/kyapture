# backend/apps/users/staff_api.py
"""
Staff area (7.5-A): users list, suspend / reactivate, audit log.

  GET   /api/v1/staff/users/                     list; ?q=<exact email> &plan= &status= &storage= &sort= &page=
  POST  /api/v1/staff/users/{id}/suspend/        {"reason": "..."}   (required, 1-300 chars, plain text)
  POST  /api/v1/staff/users/{id}/reactivate/     {"reason": "..."}   (required)
  GET   /api/v1/staff/audit/                     read-only; ?action= &page=

Staff is Django `is_staff` and nothing else (apps/core/permissions.py::IsStaffUser):
anonymous -> 401, a normal user -> 403, on every route here. The user rows carry only
what staff need (email, name, plan, storage used, collection count, joined, last login,
status); no password hash, token, PIN, unlock token, gallery password or storage key is
selected or serialized. There is no wildcard search (an exact email only), no export,
and every list is paginated and throttled per staff user.

A suspension is `is_active=False` plus the reason: that single flag already stops the
login, every token (and, here, `revoke_all_sessions` also bumps `token_version` so the
user is signed out on their very next request) and, via the public lookups, the owner's
galleries. Staff cannot suspend themselves or another staff/superuser. Each action is
audited in the same transaction (apps/users/audit.py).
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import BigIntegerField, Case, Count, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsStaffUser
from apps.photos.models import MediaAsset
from apps.subscriptions.models import FREE_PLAN_KEY, SubscriptionPlan

from . import audit
from .models import StaffAuditLog, User
from .utils import revoke_all_sessions

GIB = 1024 ** 3
NEAR_FULL_RATIO = 0.8
REASON_MAX = audit.REASON_MAX
STATUS_VALUES = ('active', 'suspended')
STORAGE_VALUES = ('empty', 'near_full', 'full')
SORT_VALUES = {'joined': '-date_joined', 'storage': '-storage_used', 'email': 'email'}


class StaffListThrottle(UserRateThrottle):
    """Reads of the staff area, per staff user id (settings rate `staff_list`)."""
    scope = 'staff_list'


class StaffActionThrottle(UserRateThrottle):
    """Suspend / reactivate, per staff user id (settings rate `staff_action`)."""
    scope = 'staff_action'


class StaffPagination(StandardResultsSetPagination):
    page_size = 25
    max_page_size = 100


def error(message, code, http_status):
    return Response({'error': message, 'code': code}, status=http_status)


# ─── the users queryset: only what the list needs ────────────────────────────

def plan_table():
    """{plan key: (name, storage_gb)} - one query for the whole page."""
    return {p.key: (p.name, p.storage_gb) for p in SubscriptionPlan.objects.all()}


def users_queryset():
    """
    Users with their live plan key, bytes stored and collection count. A plan counts
    only while its subscription is active AND unexpired (the same rule as
    get_user_subscription_metrics). Storage counts every asset row the account still
    holds (trashed galleries included), like the quota does.
    """
    live = Q(subscription__status='active', subscription__expires_at__gt=timezone.now())
    stored = (
        MediaAsset.objects.filter(gallery__photographer=OuterRef('pk'))
        .order_by().values('gallery__photographer').annotate(total=Sum('file_size')).values('total')
    )
    return User.objects.annotate(
        plan_key=Case(When(live, then=F('subscription__plan__key')), default=Value(FREE_PLAN_KEY)),
        storage_used=Coalesce(Subquery(stored, output_field=BigIntegerField()), Value(0), output_field=BigIntegerField()),
        collection_count=Count('galleries', filter=Q(galleries__is_active=True), distinct=True),
    ).only(
        # Nothing but these columns is read: never password, tokens or profile blobs.
        'id', 'email', 'username', 'display_name', 'date_joined', 'last_login',
        'is_active', 'is_staff', 'is_superuser', 'suspended_at', 'suspension_reason',
    )


class StaffUserSerializer(serializers.Serializer):
    """An explicit allowlist of output keys; built from annotated rows, never a ModelSerializer."""

    def to_representation(self, user):
        plans = self.context['plans']
        name, storage_gb = plans.get(user.plan_key) or (user.plan_key, plans.get(FREE_PLAN_KEY, ('Free', 0))[1])
        return {
            'id': str(user.pk),
            'email': user.email,
            'name': user.display_name or user.username,
            'plan': user.plan_key,
            'plan_name': name,
            'storage_used_bytes': int(user.storage_used or 0),
            'storage_limit_bytes': int(storage_gb) * GIB,
            'collection_count': user.collection_count,
            'joined': user.date_joined,
            'last_login': user.last_login,
            'status': 'active' if user.is_active else 'suspended',
            'suspended_at': user.suspended_at,
            'suspension_reason': user.suspension_reason,
            'is_staff': bool(user.is_staff or user.is_superuser),
        }


class AuditLogSerializer(serializers.ModelSerializer):
    action_label = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = StaffAuditLog
        fields = ['id', 'created_at', 'action', 'action_label', 'actor_id', 'actor_email',
                  'target_id', 'target_email', 'ip', 'reason']
        read_only_fields = fields


# ─── users list ──────────────────────────────────────────────────────────────

class StaffUserListView(APIView):
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffListThrottle]

    def get(self, request):
        params = request.query_params
        queryset = users_queryset()
        plans = plan_table()
        summary = []

        email = (params.get('q') or '').strip()
        if 'q' in params:
            # An exact address only: a fragment, a domain or a wildcard is refused, so the
            # box can never be used to page through accounts.
            try:
                if not email or len(email) > 254:
                    raise DjangoValidationError('empty')
                validate_email(email)
            except DjangoValidationError:
                return error('Search needs one complete email address.', 'invalid_email_query', status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(email__iexact=email)

        plan = params.get('plan')
        if plan:
            if plan not in plans:
                return error('Unknown plan.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(plan_key=plan)
            summary.append(f'plan={plan}')

        state = params.get('status')
        if state:
            if state not in STATUS_VALUES:
                return error('Invalid status.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(is_active=(state == 'active'))
            summary.append(f'status={state}')

        storage = params.get('storage')
        if storage:
            if storage not in STORAGE_VALUES:
                return error('Invalid storage filter.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
            # Cast to 64 bits before multiplying: the plan's GB and 2**30 are both small ints, and
            # their product overflows PostgreSQL's 32-bit integer for any plan above 1 GB.
            big = lambda number: Cast(Value(number), BigIntegerField())          # noqa: E731
            limit_gb = Case(
                *[When(plan_key=key, then=big(gb)) for key, (_, gb) in plans.items()],
                default=big(plans.get(FREE_PLAN_KEY, ('', 0))[1]), output_field=BigIntegerField(),
            )
            queryset = queryset.annotate(limit_bytes=limit_gb * big(GIB))
            if storage == 'empty':
                queryset = queryset.filter(storage_used=0)
            elif storage == 'full':
                queryset = queryset.filter(storage_used__gte=F('limit_bytes'))
            else:
                queryset = queryset.filter(storage_used__gte=F('limit_bytes') * NEAR_FULL_RATIO)
            summary.append(f'storage={storage}')

        sort = params.get('sort') or 'joined'
        if sort not in SORT_VALUES:
            return error('Invalid sort.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
        queryset = queryset.order_by(SORT_VALUES[sort], '-id')
        if sort != 'joined':
            summary.append(f'sort={sort}')

        paginator = StaffPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        # Every staff read of account data is itself audited (fail closed: no row, no data).
        if email:
            found = page[0] if page else None
            audit.record(audit.Action.USER_LOOKUP, actor=request.user, target=found, request=request,
                         reason='found' if found else 'not found')
        else:
            summary.append(f'page={paginator.page.number}')
            audit.record(audit.Action.USER_LIST, actor=request.user, request=request, reason=' '.join(summary))

        data = StaffUserSerializer(page, many=True, context={'plans': plans}).data
        return paginator.get_paginated_response(data)


# ─── suspend / reactivate ────────────────────────────────────────────────────

def read_reason(request):
    """(reason, error Response). Required, plain text, one line, at most REASON_MAX characters."""
    body = request.data if hasattr(request.data, 'get') else {}
    raw = body.get('reason')
    if not isinstance(raw, str):
        return None, error('Enter a reason.', 'reason_required', status.HTTP_400_BAD_REQUEST)
    reason = audit.one_line(raw)
    if not reason:
        return None, error('Enter a reason.', 'reason_required', status.HTTP_400_BAD_REQUEST)
    if len(reason) > REASON_MAX:
        return None, error(f'Keep the reason under {REASON_MAX} characters.', 'reason_too_long', status.HTTP_400_BAD_REQUEST)
    return reason, None


class StaffUserStateView(APIView):
    """Shared body of suspend and reactivate; `suspend` says which one the subclass is."""
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffActionThrottle]
    suspend = True

    def post(self, request, user_id):
        reason, problem = read_reason(request)
        if problem:
            return problem
        with transaction.atomic():
            target = User.objects.select_for_update().filter(pk=user_id).first()
            if target is None:
                return error('User not found.', 'not_found', status.HTTP_404_NOT_FOUND)
            if target.pk == request.user.pk:
                return error('You cannot change your own account here.', 'cannot_change_self', status.HTTP_403_FORBIDDEN)
            if target.is_staff or target.is_superuser:
                return error('Staff accounts are managed in the admin, not here.', 'cannot_change_staff',
                             status.HTTP_403_FORBIDDEN)
            if self.suspend and not target.is_active:
                return error('This account is already suspended.', 'already_suspended', status.HTTP_409_CONFLICT)
            if not self.suspend and target.is_active:
                return error('This account is not suspended.', 'not_suspended', status.HTTP_409_CONFLICT)
            self.apply(request, target, reason)
        row = users_queryset().get(pk=target.pk)
        return Response(StaffUserSerializer(row, context={'plans': plan_table()}).data)

    def apply(self, request, target, reason):
        if self.suspend:
            target.is_active = False
            target.suspended_at = timezone.now()
            target.suspension_reason = reason
            target.save(update_fields=['is_active', 'suspended_at', 'suspension_reason'])
            revoke_all_sessions(target)        # signed out on the very next request, refresh tokens dead too
            close_public_media(target)
            action = audit.Action.SUSPEND
        else:
            target.is_active = True
            target.suspended_at = None
            target.suspension_reason = ''
            target.save(update_fields=['is_active', 'suspended_at', 'suspension_reason'])
            action = audit.Action.REACTIVATE
        audit.record(action, actor=request.user, target=target, request=request, reason=reason)


class StaffUserSuspendView(StaffUserStateView):
    suspend = True


class StaffUserReactivateView(StaffUserStateView):
    suspend = False


def close_public_media(owner):
    """
    The API stops serving a suspended owner's galleries by itself (every public lookup
    checks the owner is active). The public derivative files (WebP tiers, posters,
    playback MP4s) are also public-read objects at permanent URLs, so each of the
    owner's galleries gets new random keys (the 7-B rotation) and the old URLs stop
    resolving at the storage. Reactivation needs nothing: the gallery payload hands out
    the current keys again.
    """
    from apps.galleries.models import Gallery
    from apps.photos.public_media import queue_rotation

    for gallery in Gallery.objects.filter(photographer=owner):
        queue_rotation(gallery)


# ─── audit log (read only) ───────────────────────────────────────────────────

class StaffAuditLogView(APIView):
    """GET only: there is no route, method or serializer that adds, changes or removes a row."""
    permission_classes = [IsStaffUser]
    throttle_classes = [StaffListThrottle]

    def get(self, request):
        queryset = StaffAuditLog.objects.all()
        action = request.query_params.get('action')
        if action:
            if action not in StaffAuditLog.Action.values:
                return error('Invalid action.', 'invalid_filter', status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(action=action)
        paginator = StaffPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        audit.record(audit.Action.AUDIT_VIEW, actor=request.user, request=request,
                     reason=f'action={action}' if action else '')
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)
