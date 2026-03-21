from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class AdminUITest(TestCase):
    def setUp(self) -> None:
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.client.force_login(self.admin_user)

    def test_operations_dashboard_renders(self) -> None:
        resp = self.client.get(reverse("admin:game_gamesession_dashboard"))
        assert resp.status_code == 200
        assert "Operations dashboard" in resp.content.decode()
        assert "Sync models" in resp.content.decode()

    @patch("catalog.admin.call_command")
    def test_ai_model_sync_view_runs_command(self, mock_call_command) -> None:
        resp = self.client.post(
            reverse("admin:catalog_aimodel_sync"),
            {"activate_new": "1"},
        )
        assert resp.status_code == 302
        mock_call_command.assert_called_once()
        _, kwargs = mock_call_command.call_args
        assert kwargs["activate_new"] is True
