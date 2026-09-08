from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User


class AdminAnalyticsAPITests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = User.objects.create_user(username="analytics-admin", password="pass1234", is_staff=True)
        self.user = User.objects.create_user(username="analytics-user", password="pass1234")

    def test_staff_boundary_contract_and_private_cache_headers(self) -> None:
        anonymous = self.client.get("/api/admin/analytics/")
        assert anonymous.status_code == 401
        assert anonymous["Cache-Control"] == "private, no-store"
        self.client.force_authenticate(self.user)
        forbidden = self.client.get("/api/admin/analytics/")
        assert forbidden.status_code == 403
        assert "Authorization" in forbidden["Vary"]
        self.client.force_authenticate(self.staff)
        response = self.client.get("/api/admin/analytics/")
        assert response.status_code == 200
        assert response.json()["analytics_schema_version"] == 1
        assert response.json()["summary"]["total_games"] == 0
        assert response["Cache-Control"] == "private, no-store"

    def test_filters_fail_closed(self) -> None:
        self.client.force_authenticate(self.staff)
        assert self.client.get("/api/admin/analytics/?days=0").status_code == 400
        assert self.client.get("/api/admin/analytics/?source=paid").status_code == 400
        assert self.client.get("/api/admin/analytics/?variant_slug=missing").status_code == 400
        assert self.client.get("/api/admin/analytics/?days=7&days=30").status_code == 400
        assert self.client.get("/api/admin/analytics/?extra=1").status_code == 400
