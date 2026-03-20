from django.urls import path

from .views import AIModelListView

urlpatterns = [
    path("models/", AIModelListView.as_view(), name="ai-model-list"),
]
