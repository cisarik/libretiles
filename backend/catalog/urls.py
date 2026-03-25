from django.urls import path

from .views import AIModelListView, AIPromptListView

urlpatterns = [
    path("models/", AIModelListView.as_view(), name="ai-model-list"),
    path("prompts/", AIPromptListView.as_view(), name="ai-prompt-list"),
]
