#C:\Users\LENOVO\Desktop\kyapture\backend\apps\galleries\views.py
import bcrypt
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination 

# Dynamic permission routing prevents the Storage Lockout Paradox
from apps.core.utils import get_user_subscription_metrics
from .models import Gallery
from .serializers import (
    GalleryListSerializer,
    GalleryCreateSerializer,
    GalleryDetailSerializer,
    GalleryUpdateSerializer,
)

class GalleryListPagination(PageNumberPagination):
    """
    Scoped pagination for the galleries list endpoint only (browse view).
    Global REST_FRAMEWORK PAGE_SIZE stays at 20 for every other view.

    NOTE:GallerySearchView (below)
    handles search independently of this page size, so search stays
    correct no matter how many galleries a photographer has. This value
    only affects the initial dashboard grid, which currently has no
    "load more" control. Bumped modestly above the global default so a
    Pro photographer's first screen shows more at once; a real fix
    (infinite scroll / cursor pagination for the browse view) is a
    separate, non-urgent follow-up now that search doesn't depend on it.
    """
    page_size = 60
    page_size_query_param = 'page_size'
    max_page_size = 100


class GalleryListCreateView(APIView):
    """
    GET  /api/v1/galleries/  — List all active galleries for the logged-in photographer.
    POST /api/v1/galleries/  — Create a new custom photographer gallery (Gated by Subscription) [1.1.2].
    """
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Base Query: Strict tenant isolation and pre-fetch relationship joins
        queryset = (
            Gallery.objects
            .filter(photographer=request.user, is_active=True)
            .select_related('cover_photo')
            .annotate(photo_count=Count('assets'))
        )

        # 2. Dynamic Filtering: Filter by published status if passed (e.g. ?is_published=true)
        is_published = request.query_params.get('is_published')
        if is_published is not None:
            queryset = queryset.filter(is_published=is_published.lower() in ['true', '1'])

        # 3. Dynamic Search: Case-insensitive match on title or description (e.g. ?search=wedding)
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | 
                Q(description__icontains=search_query)
            )

        # 4. Dynamic Sorting: Safe field ordering whitelist to prevent SQL injection (e.g. ?ordering=-title)
        ordering = request.query_params.get('ordering', '-created_at').strip()
        safe_ordering_fields = ['created_at', '-created_at', 'title', '-title']
        if ordering in safe_ordering_fields:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')

        # 5. Manual Pagination (APIViews do not read settings.py pagination automatically)
        paginator = GalleryListPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request, view=self)
        
        serializer = GalleryListSerializer(
            paginated_queryset,
            many=True,
            context={'request': request}
        )
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        photographer = request.user
        
        # 1. Single-pass metric calculations
        metrics = get_user_subscription_metrics(photographer)
        
        # 2. Skip limit check for administrative staff
        if not (photographer.is_superuser or photographer.is_staff):
            if metrics["max_galleries"] is not None and metrics["current_galleries_count"] >= metrics["max_galleries"]:
                return Response({
                    "error": "Gallery limit reached for your current plan.",
                    "code": "gallery_limit_reached",
                    "current_count": metrics["current_galleries_count"],
                    "plan_limit": metrics["max_galleries"],
                    "plan_name": metrics["plan_name"],
                    "message": f"You have used {metrics['current_galleries_count']} of {metrics['max_galleries']} galleries on the {metrics['plan_name']} plan. Upgrade your plan to create more."
                }, status=status.HTTP_403_FORBIDDEN)

        # 3. Instantiate the serializer exactly once
        serializer = GalleryCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            gallery = serializer.save()
            return Response(
                serializer.to_representation(gallery),
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GallerySearchView(APIView):
    """
    GET /api/v1/galleries/search/?q=<query>

    Dedicated, non-paginated search endpoint — deliberately decoupled from
    GalleryListCreateView's pagination. Search-as-you-type needs to cover
    the photographer's ENTIRE gallery set on every keystroke, not just
    whatever page size the browse view happens to be capped at. Tying
    search correctness to a page-size constant is a trap: it silently
    misses matches once someone crosses that number.

    Capped at SEARCH_RESULT_LIMIT so a broad query (e.g. a single letter)
    can't return an unbounded result set. `truncated: true` signals the
    frontend to prompt the user to refine their search rather than
    silently dropping matches beyond the cap.
    """
    permission_classes = [IsAuthenticated]

    SEARCH_RESULT_LIMIT = 100

    def get(self, request):
        query = request.query_params.get('q', '').strip()

        if not query:
            return Response({'results': [], 'count': 0, 'truncated': False}, status=status.HTTP_200_OK)

        queryset = (
            Gallery.objects
            .filter(photographer=request.user, is_active=True)
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related('cover_photo')
            .annotate(photo_count=Count('assets'))
            .order_by('-created_at')
        )

        total_count = queryset.count()
        limited_results = queryset[:self.SEARCH_RESULT_LIMIT]

        serializer = GalleryListSerializer(
            limited_results, many=True, context={'request': request}
        )

        return Response({
            'results': serializer.data,
            'count': total_count,
            'truncated': total_count > self.SEARCH_RESULT_LIMIT,
        }, status=status.HTTP_200_OK)
class GalleryDetailView(APIView):
    """
    GET    /api/v1/galleries/{slug}/  — View detailed settings of a specific gallery.
    PUT    /api/v1/galleries/{slug}/  — Update settings or cover photo parameters.
    DELETE /api/v1/galleries/{slug}/  — Soft-delete gallery (mark is_active=False) [1.1.2].
    
    NOTE: Left with IsAuthenticated permission to allow expired users to edit/delete 
    assets to cleanly manage their database footprint and resolve plan limit blocks.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, slug, user):
        """
        Retrieves a single gallery. Scopes lookup to active galleries 
        belonging strictly to the requesting user [1.1.2].
        """
        try:
            return (
                Gallery.objects
                .select_related('cover_photo')
                .annotate(photo_count=Count('assets'))
                .get(slug=slug, photographer=user, is_active=True)
            )
        except Gallery.DoesNotExist:
            return None

    def get(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            # Mask the error as 404 to prevent enumeration attacks [1.1.2]
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = GalleryDetailSerializer(
            gallery,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    def patch(self, request, slug):
        """
        PATCH /api/v1/galleries/{slug}/
        Surgically forwards partial settings updates to the PUT handler.
        """
        return self.put(request, slug)

    def put(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = GalleryUpdateSerializer(
            gallery,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            updated_gallery = serializer.save()
            return Response(
                serializer.to_representation(updated_gallery),
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Safe Soft-Delete: Never hard-delete client delivery assets [1.1.2]
        gallery.is_active = False
        gallery.save()
        
        return Response(
            {'message': 'Gallery deleted successfully.'},
            status=status.HTTP_200_OK
        )
        

class DashboardStatsView(APIView):
    """
    GET /api/v1/galleries/dashboard/stats/

    Returns complete dashboard analytics for the logged-in photographer.
    Uses our single-pass metrics utility to keep the database footprint at O(1)
    while matching Claude's frontend contract keys perfectly.

    David uses this to render:
    - Storage progress bar (used vs limit)
    - Gallery slots badge
    - Expiration warning banners
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        photographer = request.user
        from django.utils import timezone
        from apps.photos.models import MediaAsset
        from apps.subscriptions.models import UserSubscription

        # 1. Fetch single-pass subscription limits and usage metrics from PostgreSQL
        metrics = get_user_subscription_metrics(photographer)

        # 2. Count total media assets (both photos and videos) across all active galleries
        photos_used = MediaAsset.objects.filter(
            gallery__photographer=photographer,
            gallery__is_active=True
        ).count()

        # 3. Resolve active subscription expiration parameters safely
        days_remaining = 0
        expires_at = None
        subscription_status = "no_subscription"

        try:
            sub = UserSubscription.objects.get(user=photographer, status='active')
            subscription_status = sub.status
            if sub.expires_at:
                expires_at = sub.expires_at
                if sub.expires_at > timezone.now():
                    days_remaining = (sub.expires_at - timezone.now()).days
        except UserSubscription.DoesNotExist:
            pass

        # 4. Handle Admin Bypass case cleanly
        if photographer.is_superuser or photographer.is_staff:
            return Response({
                'galleries_used': metrics["current_galleries_count"],
                'photos_used': photos_used,
                'storage_used_bytes': metrics["current_total_storage_bytes"],
                'storage_used_gb': round(metrics["current_total_storage_bytes"] / (1024 ** 3), 2),
                'plan_name': 'Admin',
                'plan_gallery_limit': None,
                'plan_photo_limit': None,
                'plan_storage_limit_gb': None,
                'plan_storage_limit_bytes': None,
                'galleries_remaining': None,
                'storage_remaining_gb': None,
                'subscription_status': 'admin',
                'expires_at': None,
                'days_remaining': None,
            }, status=status.HTTP_200_OK)

        # 5. Handle Unsubscribed case cleanly (No crash, returns zero bounds)
        if subscription_status == "no_subscription":
            storage_used_bytes = metrics["current_total_storage_bytes"]
            plan_storage_bytes = metrics["storage_bytes_limit"]
            storage_remaining_gb = round(
                max(0.0, (plan_storage_bytes - storage_used_bytes) / (1024 ** 3)), 2
            )
            return Response({
                'galleries_used': metrics["current_galleries_count"],
                'photos_used': photos_used,
                'storage_used_bytes': storage_used_bytes,
                'storage_used_gb': round(storage_used_bytes / (1024 ** 3), 2),
                'plan_name': metrics["plan_name"],
                'plan_gallery_limit': metrics["max_galleries"],
                'plan_photo_limit': metrics["max_photos_per_gallery"],
                'plan_storage_limit_gb': plan_storage_bytes / (1024 ** 3),
                'plan_storage_limit_bytes': plan_storage_bytes,
                'galleries_remaining': None,
                'storage_remaining_gb': storage_remaining_gb,
                'allow_video': metrics["allow_video"],
                'subscription_status': 'no_subscription',
                'expires_at': None,
                'days_remaining': None,
            }, status=status.HTTP_200_OK)

        # 6. Calculate Remaining Quotas
        storage_used_bytes = metrics["current_total_storage_bytes"]
        plan_storage_bytes = metrics["storage_bytes_limit"]
        
        galleries_remaining = max(0, metrics["max_galleries"] - metrics["current_galleries_count"])
        storage_remaining_gb = round(
            max(0.0, (plan_storage_bytes - storage_used_bytes) / (1024 ** 3)), 
            2
        )

        # 7. Deliver the structured JSON payload matching David's exact key mappings
        return Response({
            'galleries_used': metrics["current_galleries_count"],
            'photos_used': photos_used,
            'storage_used_bytes': storage_used_bytes,
            'storage_used_gb': round(storage_used_bytes / (1024 ** 3), 2),
            
            'plan_name': metrics["plan_name"],
            'plan_gallery_limit': metrics["max_galleries"],
            'plan_photo_limit': metrics["max_photos_per_gallery"],
            'plan_storage_limit_gb': metrics["storage_bytes_limit"] / (1024 ** 3),
            'plan_storage_limit_bytes': plan_storage_bytes,
            
            'galleries_remaining': galleries_remaining,
            'storage_remaining_gb': storage_remaining_gb,
            
            'subscription_status': subscription_status,
            'expires_at': expires_at,
            'days_remaining': days_remaining,
        }, status=status.HTTP_200_OK)

class GalleryPublishView(APIView):
    """
    POST /api/v1/galleries/{slug}/publish/
    
    Allows the authenticated photographer to dynamically publish or unpublish 
    a specific gallery container.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        gallery = get_object_or_404(
            Gallery, 
            slug=slug, 
            photographer=request.user, 
            is_active=True
        )
        
        # Expects a boolean flag 'is_published' in the request payload
        is_published = request.data.get('is_published', True)
        gallery.is_published = is_published
        gallery.save(update_fields=['is_published'])
        
        return Response({
            'status': 'success', 
            'is_published': gallery.is_published
        }, status=status.HTTP_200_OK)


class GallerySetPasswordView(APIView):
    """
    POST /api/v1/galleries/{slug}/set-password/
    
    Allows the authenticated photographer to enable, disable, or modify 
    the access-password security parameters of a specific gallery.
    
    SECURITY: Every successful call revokes all existing ClientSession rows
    for this gallery. Without this, validate_session_token() (apps/clients/
    views.py) has no way to know a session was issued under a now-stale
    password — it only checks (access_token, gallery) — so anyone who had
    already unlocked the gallery would silently keep access forever, even
    after the photographer rotated the password specifically to cut them
    off (leaked link, ex-client, etc).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        gallery = get_object_or_404(
            Gallery, 
            slug=slug, 
            photographer=request.user, 
            is_active=True
        )
        
        # Safely extract password, converting NoneType to empty string
        password = request.data.get('password')
        password = password.strip() if password else ''
        
        
        # Deferred import: avoids a module-load-time circular dependency
        # between apps.galleries.views and apps.clients.models (the two
        # apps don't otherwise import each other at import time).
        
        from apps.clients.models import ClientSession


        # 1. If password is empty, interpret as removing password-protection entirely
        if not password:
            gallery.is_password_protected = False
            gallery.password_hash = None
            gallery.save(update_fields=['is_password_protected', 'password_hash'])
            
            # Revoke every session tied to this gallery. Technically the
            # gallery is now open to anyone regardless of token, but we
            # clear these anyway so a stale access_token is never treated
            # as meaningful once the password state has changed underneath it.
            
            revoked_count, _ = ClientSession.objects.filter(gallery=gallery).delete()

            
            return Response({
                'status': 'success',
                'is_password_protected': gallery.is_password_protected,
                'has_password': False,
                'revoked_sessions': revoked_count,
            }, status=status.HTTP_200_OK)

        # 2. If password exists, hash utilizing raw bcrypt salting
        gallery.is_password_protected = True
        gallery.password_hash = bcrypt.hashpw(
            password.encode('utf-8'), 
            bcrypt.gensalt()
        ).decode('utf-8')
        
        gallery.save(update_fields=['is_password_protected', 'password_hash'])
        
        # Revoke every session issued under the OLD password. This is the
        # actual security fix (H-4): without it, everyone who already
        # unlocked the gallery keeps their access_token valid indefinitely —
        # the password change accomplishes nothing for them.
        revoked_count, _ = ClientSession.objects.filter(gallery=gallery).delete()
        

        
        return Response({
            'status': 'success',
            'is_password_protected': gallery.is_password_protected,
            'has_password': True,
            'revoked_sessions': revoked_count, 
        }, status=status.HTTP_200_OK)