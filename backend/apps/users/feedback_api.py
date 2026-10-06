# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/feedback_api.py
"""
User feedback: POST /api/v1/feedback/ and the staff inbox.

  POST   /feedback/                  any signed-in user submits (throttled per USER)
  GET    /feedback/mine/             the caller's own submissions only
  GET    /feedback/inbox/            staff only, newest first, ?status= &category=
  PATCH  /feedback/inbox/{id}/       staff only, changes `status` and nothing else

Every client-sent field is untrusted. Text is trimmed, length-capped and stored as
plain text (never marked safe; the JSON API returns it as is, so a UI must render
it escaped). The only auto-captured context is the route PATH (query string and
fragment dropped, token-like segments masked), the gallery slug, an allowlisted
app version and an allowlisted browser class read from the User-Agent header.
Tokens, cookies, signed URLs and PINs are never read or stored. No attachments.

Staff is Django `is_staff`; there is no separate role. A foreign or random id on
the PATCH is a plain 404, so the inbox does not confirm which ids exist.
"""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination

from .models import Feedback
from .notification_service import notify_staff_feedback

ROUTE_CHARS = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
SLUG_CHARS = re.compile(r'^[A-Za-z0-9_-]{1,225}$')
UUID_SEGMENT = re.compile(r'^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$')
LONG_TOKEN_SEGMENT = re.compile(r'^[A-Za-z0-9_-]{32,}$')
RESET_TOKEN_SEGMENT = re.compile(r'^[0-9a-z]{1,13}-[0-9a-f]{20,}$')    # Django password-reset token


def clean_route(value):
    """
    Path only. Everything after `?` or `#` is dropped (it can hold tokens or
    PINs), a full URL is reduced to its path, anything that is not a plain
    path is discarded, and id/token-looking segments become `:id` / `:token`.
    """
    if not isinstance(value, str):
        return ''
    value = value.strip()
    value = value.split('#', 1)[0].split('?', 1)[0]
    if '://' in value or value.startswith('//'):
        value = urlsplit(value).path
    if not value.startswith('/') or not ROUTE_CHARS.match(value):
        return ''
    segments = []
    for segment in value.split('/'):
        if UUID_SEGMENT.match(segment):
            segment = ':id'
        elif LONG_TOKEN_SEGMENT.match(segment) or RESET_TOKEN_SEGMENT.match(segment):
            segment = ':token'
        segments.append(segment)
    return '/'.join(segments)[:Feedback.ROUTE_MAX]


def clean_slug(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    return value if SLUG_CHARS.match(value) else ''


def clean_app_version(value):
    """Kept only when it is one of the versions this deployment knows; never free text."""
    allowed = {settings.APP_VERSION, *settings.FEEDBACK_ACCEPTED_APP_VERSIONS}
    if isinstance(value, str) and value.strip() in allowed:
        return value.strip()[:32]
    return 'unknown'


def browser_class(user_agent):
    """Maps the User-Agent header onto the Feedback.Browser allowlist (order matters: Edge/Opera say Chrome too)."""
    ua = (user_agent or '').lower()
    B = Feedback.Browser
    if 'edg/' in ua or 'edga/' in ua or 'edgios/' in ua:
        return B.EDGE
    if 'opr/' in ua or 'opera' in ua:
        return B.OPERA
    if 'firefox/' in ua or 'fxios/' in ua:
        return B.FIREFOX
    if 'chrome/' in ua or 'crios/' in ua:
        return B.CHROME
    if 'safari/' in ua:
        return B.SAFARI
    return B.OTHER


class IsStaffUser(BasePermission):
    """Django is_staff on an active account."""
    message = 'Staff access required.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)


class FeedbackRateThrottle(UserRateThrottle):
    """Per authenticated user id (rate from settings REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['feedback']); never per IP."""
    scope = 'feedback'

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}


class FeedbackCreateSerializer(serializers.Serializer):
    """Unknown keys (status, user, browser_class ...) are ignored, never applied."""
    category = serializers.ChoiceField(choices=Feedback.Category.choices)
    subject = serializers.CharField(max_length=Feedback.SUBJECT_MAX, required=False, allow_blank=True, default='')
    message = serializers.CharField(max_length=Feedback.MESSAGE_MAX)
    route = serializers.JSONField(required=False)
    gallery_slug = serializers.JSONField(required=False)
    app_version = serializers.JSONField(required=False)

    def validate_subject(self, value):
        # A subject is one line: fold any line breaks into spaces.
        return ' '.join(value.split())


class FeedbackSerializer(serializers.ModelSerializer):
    """What the submitter sees of their own rows."""
    class Meta:
        model = Feedback
        fields = ['id', 'category', 'subject', 'message', 'route', 'gallery_slug', 'status', 'created_at', 'updated_at']
        read_only_fields = fields


class FeedbackInboxSerializer(FeedbackSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta(FeedbackSerializer.Meta):
        fields = FeedbackSerializer.Meta.fields + ['app_version', 'browser_class', 'user_email', 'username']
        read_only_fields = fields


class FeedbackStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Feedback.Status.choices)


class FeedbackPagination(StandardResultsSetPagination):
    page_size = 20
    max_page_size = 100


class FeedbackCreateView(APIView):
    """POST /api/v1/feedback/ — signed-in users only; throttled per user."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [FeedbackRateThrottle]

    def post(self, request):
        serializer = FeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            feedback = Feedback.objects.create(
                user=request.user,
                category=data['category'],
                subject=data['subject'],
                message=data['message'],
                route=clean_route(data.get('route')),
                gallery_slug=clean_slug(data.get('gallery_slug')),
                app_version=clean_app_version(data.get('app_version')),
                browser_class=browser_class(request.META.get('HTTP_USER_AGENT', '')),
            )
            notify_staff_feedback(feedback)
        return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


class MyFeedbackListView(APIView):
    """GET /api/v1/feedback/mine/ — only the caller's own submissions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        paginator = FeedbackPagination()
        page = paginator.paginate_queryset(Feedback.objects.filter(user=request.user), request, view=self)
        return paginator.get_paginated_response(FeedbackSerializer(page, many=True).data)


class FeedbackInboxListView(APIView):
    """GET /api/v1/feedback/inbox/?status=&category=&page= — staff only, newest first."""
    permission_classes = [IsStaffUser]

    def get(self, request):
        queryset = Feedback.objects.select_related('user')
        for param, choices in (('status', Feedback.Status), ('category', Feedback.Category)):
            value = request.query_params.get(param)
            if value:
                if value not in choices.values:
                    return Response({'error': f'Invalid {param}.', 'code': 'invalid_filter'}, status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(**{param: value})
        paginator = FeedbackPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(FeedbackInboxSerializer(page, many=True).data)


class FeedbackInboxDetailView(APIView):
    """PATCH /api/v1/feedback/inbox/{id}/ — staff only; `status` is the only writable field."""
    permission_classes = [IsStaffUser]

    def patch(self, request, feedback_id):
        feedback = Feedback.objects.select_related('user').filter(pk=feedback_id).first()
        if feedback is None:
            return Response({'error': 'Feedback not found.', 'code': 'not_found'}, status=status.HTTP_404_NOT_FOUND)
        body = request.data if hasattr(request.data, 'keys') else {}
        extra = sorted(set(body.keys()) - {'status'})
        if extra:
            return Response(
                {'error': 'Only status can be changed.', 'code': 'read_only_fields', 'fields': extra},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = FeedbackStatusSerializer(data=body)
        serializer.is_valid(raise_exception=True)
        feedback.status = serializer.validated_data['status']
        feedback.save(update_fields=['status', 'updated_at'])
        return Response(FeedbackInboxSerializer(feedback).data)
