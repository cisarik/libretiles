from django.urls import path

from .views import ChargeAITurnView

urlpatterns: list = [
    path("charge-ai-turn/", ChargeAITurnView.as_view(), name="charge-ai-turn"),
]
