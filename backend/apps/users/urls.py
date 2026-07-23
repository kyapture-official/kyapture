from django.urls import path
from .views import (
    RegisterView, LoginView, LogoutView,
    CookieTokenRefreshView,  
    PasswordResetRequestView,
    PasswordResetConfirmView,  
    MeView, ChangePasswordView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset'),  
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),  
    path('me/', MeView.as_view(), name='auth-me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-pw'),
]