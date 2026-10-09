# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/serializers.py
import logging
import re
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework import serializers
from apps.core.branding import InvalidLogo, sanitize_avatar_upload, sanitize_logo_upload
from apps.users.collection_defaults import validate_collection_defaults
from apps.subscriptions.entitlements import BRANDING, require_feature
from . import audit
from .models import User
from .password_policy import password_problems
from .tokens import VersionedRefreshToken

logger = logging.getLogger(__name__)

# List of reserved system subdomains to prevent hijacking/spoofing
RESERVED_USERNAMES = {
    'admin', 'api', 'app', 'www', 'mail', 'blog', 'support', 'billing',
    'root', 'static', 'media', 'domain', 'kaypture', 'test', 'dev'
}

# Enforces RFC-compliant, URL-safe subdomains (lowercase alphanumeric, with single internal dashes)
USERNAME_REGEX = re.compile(r'^[a-z0-9](-?[a-z0-9])*$')

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializes complete User profile data.
    Protects read-only fields from administrative or photographer manipulation.
    """
    # Computed from the live subscription (active AND unexpired), the single entitlement rule, not read from
    # the legacy column: a lapsed plan is Free at once and an approved payment is Pro at once (7.5-B).
    is_active_plan = serializers.SerializerMethodField()

    def get_is_active_plan(self, user):
        from apps.subscriptions.entitlements import has_live_paid_plan
        return has_live_paid_plan(user)

    # 7.5-E: null, or {requested_at, scheduled_for} while an account deletion is waiting (the app then shows
    # the "Cancel deletion" page instead of the dashboard). Read only.
    deletion = serializers.SerializerMethodField()

    def get_deletion(self, user):
        if user.deletion_requested_at is None:
            return None
        return {'requested_at': user.deletion_requested_at, 'scheduled_for': user.deletion_scheduled_for}

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'display_name',
            'bio', 'avatar', 'logo', 'branding_color',
            'phone', 'website', 'is_active_plan', 'is_staff', 'created_at', 'deletion'
        ]
        # is_staff is shown only so the UI can offer the staff feedback inbox; it can
        # never be written here, and the inbox endpoints enforce it server-side.
        read_only_fields = ['id', 'email', 'is_active_plan', 'is_staff', 'created_at', 'deletion']
        # Uniqueness is enforced by validate_username below (case-normalized,
        # excluding the user's own row, with the app's own wording); the model's
        # generic UniqueValidator would answer first with "user with this
        # username already exists." and duplicate that check.
        extra_kwargs = {'username': {'validators': []}}

    def validate_username(self, value):
        clean_username = value.strip().lower()
        if clean_username in RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved for system administration.")
        if not USERNAME_REGEX.match(clean_username):
            raise serializers.ValidationError(
                "Username must be lowercase, alphanumeric, and can only contain single dashes."
            )
        query_set = User.objects.filter(username=clean_username)
        if self.instance:
            query_set = query_set.exclude(id=self.instance.id)
        if query_set.exists():
            raise serializers.ValidationError("This username is already taken.")
        return clean_username

    def validate_branding_color(self, value):
        if value and not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise serializers.ValidationError('Color must be a valid hex code (e.g., #FF5733).')
        return value

    def validate_display_name(self, value):
        """The name clients see on every gallery (studio / business name). Plain text, required."""
        from apps.core.utils import sanitize_text
        clean = sanitize_text(value or '').strip()
        if not clean:
            raise serializers.ValidationError('Display name is required.')
        return clean

    def validate_bio(self, value):
        from apps.core.utils import sanitize_text
        return sanitize_text(value or '').strip()

    def validate_phone(self, value):
        value = (value or '').strip()
        if value and not re.match(r'^[0-9+()\-.\s]{3,20}$', value):
            raise serializers.ValidationError('Enter a valid phone number (digits, spaces and + - ( ) only).')
        return value

    def validate_avatar(self, value):
        """The profile picture is shown on the public portfolio: validated and re-encoded like the logo."""
        if value is None:
            return value
        try:
            return sanitize_avatar_upload(value)
        except InvalidLogo as exc:
            raise serializers.ValidationError(str(exc))

    def to_internal_value(self, data):
        """
        Check the Branding entitlement BEFORE any field parses the upload.
        DRF's ImageField decodes the file with Pillow during field
        validation, which would otherwise run on an untrusted file for an
        account that is not allowed to upload one, and answer a Free user's
        bad file with a 400 instead of the real reason (403).
        """
        if self.instance is not None and hasattr(data, 'get') and data.get('logo') not in (None, ''):
            require_feature(self.instance, BRANDING)
        return super().to_internal_value(data)

    def validate_logo(self, value):
        """
        Branding is a Pro+ feature, enforced HERE (server-side) — the settings
        UI's locked state is only a courtesy. Setting/replacing a logo needs
        the entitlement; removing one (value is None) never does, so a
        photographer whose plan lapsed can still clean up. The upload itself
        is validated by Pillow and re-encoded (see apps/core/branding.py).
        """
        if value is None:
            return value
        require_feature(self.instance, BRANDING)
        try:
            return sanitize_logo_upload(value)
        except InvalidLogo as exc:
            raise serializers.ValidationError(str(exc))

    def update(self, instance, validated_data):
        previous_logo = instance.logo.name if instance.logo else None
        instance = super().update(instance, validated_data)
        if 'logo' in validated_data and previous_logo:
            current_logo = instance.logo.name if instance.logo else None
            if previous_logo != current_logo:
                # Unique key per upload (see get_branding_logo_path), so the
                # old file is now an orphan — delete it. Never let a storage
                # hiccup fail the profile save the user just made.
                try:
                    instance.logo.storage.delete(previous_logo)
                except Exception:
                    logger.exception('Failed to delete replaced branding logo %s', previous_logo)
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles secure photographer registration.
    Enforces password strength validation and protects the platform subdomain namespace [1.1.2].
    """
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    # Declare fields explicitly to allow clean optional parameters during registration
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    website = serializers.URLField(required=False, allow_null=True, default=None)
    class Meta:
        model = User
        fields = ['email', 'username', 'phone', 'website', 'display_name', 'password', 'password2']

    def validate_email(self, value):
        """Sanitizes and normalizes the email, then checks for global database uniqueness."""
        clean_email = value.strip().lower()
        if User.objects.filter(email=clean_email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return clean_email

    def validate_username(self, value):
        """Validates that the username is a secure, unique, and URL-safe subdomain."""
        clean_username = value.strip().lower()
        
        if clean_username in RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved.")
            
        if not USERNAME_REGEX.match(clean_username):
            raise serializers.ValidationError(
                "Username must contain only lowercase, alphanumeric, characters and single internal dashes."
            )
            
        if User.objects.filter(username=clean_username).exists():
            raise serializers.ValidationError("This username is already taken.")
            
        return clean_username

    def validate(self, data):
        """Performs password match checks and runs Django's native strength validator [1.1.2]."""
        # Password match check
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
            
        # The one password policy (apps/users/password_policy.py), shared with
        # password change and reset. The unsaved instance lets the similarity
        # check see the username and email.
        user_instance = User(username=data.get('username'), email=data.get('email'))
        problems = password_problems(data['password'], user_instance)
        if problems:
            raise serializers.ValidationError({'password': problems})
            
        return data

    def create(self, validated_data):
        """Creates the active photographer account using custom manager."""
        validated_data.pop('password2')
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    """
    Authenticates photographer credentials.
    Generates and returns JWT access/refresh tokens alongside their profile metadata [1.1.2].
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        clean_email = data.get('email').strip().lower()
        password = data.get('password')

        # authenticate() evaluates clean parameters against the database hashes
        user = authenticate(
            request=self.context.get('request'),
            username=clean_email,
            password=password
        )
        
        if not user:
            # 7.5-A: Django refuses an inactive account the same way as a wrong password.
            # Only someone who typed the RIGHT password learns that the account is suspended.
            suspended = User.objects.filter(email=clean_email, is_active=False).first()
            if suspended is not None and suspended.check_password(password):
                if suspended.deletion_started_at is not None:        # 7.5-E: the purge has begun
                    raise serializers.ValidationError({'non_field_errors': 'This account is being deleted and can no longer be used.'})
                raise serializers.ValidationError({'non_field_errors': 'This account has been suspended. Contact support.'})
            raise serializers.ValidationError({'non_field_errors': 'Invalid email or password.'})
            
        if not user.is_active:
            raise serializers.ValidationError({'non_field_errors': 'This account has been disabled.'})

        # "Last login" in the staff list: a real value, set on a successful sign-in only.
        update_last_login(None, user)

        # Generate standard JWT session and refresh tokens
        refresh = VersionedRefreshToken.for_user(user)

        # Connect and return the user profile directly to optimize David's frontend [1.1.2]
        return {
            'user': UserProfileSerializer(user, context=self.context).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


class ChangePasswordSerializer(serializers.Serializer):
    """
    Validates and changes active user passwords securely.
    """
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({'new_password2': 'New passwords do not match.'})

        problems = password_problems(data['new_password'], self.context['request'].user)
        if problems:
            raise serializers.ValidationError({'new_password': problems})

        return data

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()

        # 7-C: every session of the account ends here, this device's included
        # (ChangePasswordView then gives this device a fresh session), and the
        # owner is told by email. See revoke_all_sessions (apps/users/utils.py).
        from .password_reset import queue_password_changed_email
        from .utils import revoke_all_sessions
        revoke_all_sessions(user)
        queue_password_changed_email(user, 'change')
        audit.record_event(
            audit.Action.PASSWORD_CHANGE, actor=user, target=user, request=self.context.get('request'), reason='self',
        )

        return user


# ─────────────────────────────────────────────────────────────
# SETTINGS: notifications / privacy / collection defaults
# GET/PATCH /api/v1/auth/settings/
# ─────────────────────────────────────────────────────────────

class _StrictSerializer(serializers.Serializer):
    """Rejects unknown keys, so a typo or a probe for a privileged field can never look like a saved setting."""

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unknown = set(data.keys()) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: 'Unknown setting.' for key in sorted(unknown)})
        return super().to_internal_value(data)


class NotificationPreferencesSerializer(_StrictSerializer):
    downloads = serializers.BooleanField(required=False)
    favorites = serializers.BooleanField(required=False)
    payments = serializers.BooleanField(required=False)


class PrivacySettingsSerializer(_StrictSerializer):
    portfolio_public = serializers.BooleanField(required=False)


class UserSettingsSerializer(_StrictSerializer):
    """
    The settings that have a backend home: notification preferences, privacy,
    and Collection Defaults. Always scoped to request.user (the view passes
    the instance); there is no id in the URL or body to manipulate.
    """
    notifications = NotificationPreferencesSerializer(required=False)
    privacy = PrivacySettingsSerializer(required=False)
    collection_defaults = serializers.JSONField(required=False)

    FIELD_MAP = {
        'downloads': 'notify_downloads',
        'favorites': 'notify_favorites',
        'payments': 'notify_payments',
    }

    def validate_collection_defaults(self, value):
        clean, errors = validate_collection_defaults(value)
        if errors:
            raise serializers.ValidationError(errors)
        if clean.get('watermark_enabled') and not (self.instance.collection_defaults or {}).get('watermark_enabled'):
            # Newly switching the watermark default ON is a Pro+ action; leaving
            # an existing value, or switching it off, never is.
            from apps.subscriptions.entitlements import WATERMARK, require_feature
            require_feature(self.instance, WATERMARK)
        return clean

    def to_representation(self, user):
        from apps.users.collection_defaults import get_collection_defaults
        return {
            'notifications': {
                'downloads': user.notify_downloads,
                'favorites': user.notify_favorites,
                'payments': user.notify_payments,
            },
            'privacy': {'portfolio_public': user.portfolio_public},
            'collection_defaults': get_collection_defaults(user),
        }

    def update(self, user, validated_data):
        fields = []
        for public_name, value in (validated_data.get('notifications') or {}).items():
            setattr(user, self.FIELD_MAP[public_name], value)
            fields.append(self.FIELD_MAP[public_name])
        for public_name, value in (validated_data.get('privacy') or {}).items():
            setattr(user, public_name, value)
            fields.append(public_name)
        if 'collection_defaults' in validated_data:
            user.collection_defaults = validated_data['collection_defaults']
            fields.append('collection_defaults')
        if fields:
            user.save(update_fields=fields)
        return user
