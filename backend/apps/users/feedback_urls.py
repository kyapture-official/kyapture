# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/feedback_urls.py
from django.urls import path

from .feedback_api import (
    FeedbackCreateView,
    FeedbackInboxDetailView,
    FeedbackInboxListView,
    MyFeedbackListView,
)

urlpatterns = [
    path('', FeedbackCreateView.as_view(), name='feedback-create'),
    path('mine/', MyFeedbackListView.as_view(), name='feedback-mine'),
    path('inbox/', FeedbackInboxListView.as_view(), name='feedback-inbox'),
    path('inbox/<uuid:feedback_id>/', FeedbackInboxDetailView.as_view(), name='feedback-inbox-detail'),
]
