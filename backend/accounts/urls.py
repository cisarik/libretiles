from django.urls import path

from .views import (
    ChangePasswordView,
    LogoutView,
    MeView,
    RegisterView,
    ScopedTokenObtainPairView,
    ScopedTokenRefreshView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", ScopedTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", ScopedTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
