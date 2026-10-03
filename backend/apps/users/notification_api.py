# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/notification_api.py
"""
The photographer's dashboard bell: GET /api/v1/notifications/ and friends.

Every query is scoped to request.user, so there is no way to read or mark
another account's notifications; a foreign or random id is a plain 404 (the same
answer as a notification that doesn't exist), never a 403 that would confirm it.
"""
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination

from .models import Notification
from .notification_service import notification_link


class NotificationSerializer(serializers.ModelSerializer):
    link = serializers.SerializerMethodField()
    gallery_slug = serializers.SerializerMethodField()
    # `updated_at` moves when a burst of events coalesces into the row, so it is
    # the "last activity" time the bell should sort and display by.
    timestamp = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'kind', 'message', 'count', 'is_read', 'timestamp', 'created_at', 'link', 'gallery_slug']
        read_only_fields = fields

    def get_link(self, obj):
        return notification_link(obj)

    def get_gallery_slug(self, obj):
        return obj.gallery.slug if obj.gallery_id else None


class NotificationPagination(StandardResultsSetPagination):
    page_size = 15
    max_page_size = 50


def _unread_count(user):
    return Notification.objects.filter(user=user, is_read=False).count()


class NotificationListView(APIView):
    """GET /api/v1/notifications/?page=&unread=1 — newest activity first, paginated."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Notification.objects.filter(user=request.user).select_related('gallery')
        if request.query_params.get('unread') in ('1', 'true'):
            queryset = queryset.filter(is_read=False)
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(NotificationSerializer(page, many=True).data)
        response.data['unread_count'] = _unread_count(request.user)
        return response


class NotificationUnreadCountView(APIView):
    """GET /api/v1/notifications/unread-count/ — one indexed COUNT, cheap enough to poll."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'unread_count': _unread_count(request.user)})


class NotificationReadView(APIView):
    """POST /api/v1/notifications/{id}/read/ — idempotent; persists server-side."""
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        notification = Notification.objects.filter(pk=notification_id, user=request.user).first()
        if notification is None:
            return Response({'error': 'Notification not found.', 'code': 'not_found'}, status=status.HTTP_404_NOT_FOUND)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at', 'updated_at'])
        return Response({'id': str(notification.pk), 'is_read': True, 'unread_count': _unread_count(request.user)})


class NotificationReadAllView(APIView):
    """POST /api/v1/notifications/read-all/ — marks only the caller's unread rows."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        marked = Notification.objects.filter(user=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({'marked': marked, 'unread_count': 0})
