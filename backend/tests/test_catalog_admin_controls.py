from __future__ import annotations

import re
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from catalog.admin import AIModelAdmin
from catalog.admin_controls import (
    EMPTY_FLAG_OFF_MESSAGE,
    EMPTY_FLAG_ON_MESSAGE,
    LAST_TOOLS_MESSAGE,
    STALE_REVIEW_MESSAGE,
    CatalogChange,
    CatalogControlError,
    apply_reviewed_changes,
    apply_reviewed_token,
    catalog_fingerprint,
    sign_review_token,
)
from catalog.models import AIModel, CatalogAdminControl
from catalog.openrouter_sync import OpenRouterModelRecord, sync_openrouter_models
from catalog.selection import (
    DIRECT_FREE_RIVAL_PAIRS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
    WATCHLIST_FREE_RIVAL_PAIRS,
    get_selectable_models,
)


def _staff(*codenames: str) -> User:
    user = User.objects.create_user(
        username=f"admin-staff-{User.objects.count()}",
        password="x",
        is_staff=True,
    )
    user.user_permissions.add(
        *Permission.objects.filter(content_type__app_label="catalog", codename__in=codenames)
    )
    return user


def _formset(
    rows: list[AIModel],
    overrides: dict[int, tuple[bool, int]] | None = None,
) -> dict[str, str]:
    data = {
        "form-TOTAL_FORMS": str(len(rows)),
        "form-INITIAL_FORMS": str(len(rows)),
    }
    for index, model in enumerate(rows):
        active, order = model.is_active, model.sort_order
        if overrides and model.pk in overrides:
            active, order = overrides[model.pk]
        data[f"form-{index}-id"] = str(model.pk)
        if active:
            data[f"form-{index}-is_active"] = "on"
        data[f"form-{index}-sort_order"] = str(order)
    return data


def _token(html: str) -> str:
    match = re.search(r'name="review_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _all_rows() -> list[AIModel]:
    return list(AIModel.objects.order_by("sort_order", "id")[:100])


def _active_tools_count() -> int:
    return len(
        [
            model
            for model in AIModel.objects.filter(is_active=True, model_type="language")
            if isinstance(model.tags, list) and "tools" in model.tags
        ]
    )


class CatalogAdminControlTests(TestCase):
    def setUp(self) -> None:
        call_command("seed_models", stdout=StringIO())
        self.user = _staff("change_aimodel", "view_aimodel", "probe_aimodel")
        self.client = Client()
        self.client.force_login(self.user)
        self.review_url = reverse("admin:catalog_aimodel_controls_review")
        self.apply_url = reverse("admin:catalog_aimodel_controls_apply")
        self.controls_url = reverse("admin:catalog_aimodel_controls")

    def _review(self, overrides: dict[int, tuple[bool, int]] | None = None) -> str:
        response = self.client.post(self.review_url, _formset(_all_rows(), overrides))
        assert response.status_code == 200
        return _token(response.content.decode())

    def test_f08_last_tools_row_refusal_and_replacement_batch(self) -> None:
        tools = [
            model
            for model in AIModel.objects.filter(model_type="language").order_by("id")
            if isinstance(model.tags, list) and "tools" in model.tags
        ]
        keep, replacement = tools[0], tools[1]
        overrides = {model.pk: (False, model.sort_order) for model in tools}
        overrides[keep.pk] = (True, keep.sort_order)
        token = self._review(overrides)
        apply = self.client.post(self.apply_url, {"review_token": token})
        assert apply.status_code == 302
        keep.refresh_from_db()
        assert keep.is_active is True

        overrides = {model.pk: (False, model.sort_order) for model in _all_rows()}
        token = self._review(overrides)
        refused = self.client.post(self.apply_url, {"review_token": token})
        assert refused.status_code == 409
        assert LAST_TOOLS_MESSAGE.encode() in refused.content
        keep.refresh_from_db()
        assert keep.is_active is True

        overrides = {model.pk: (model.is_active, model.sort_order) for model in _all_rows()}
        overrides[keep.pk] = (False, keep.sort_order)
        overrides[replacement.pk] = (True, replacement.sort_order)
        token = self._review(overrides)
        swapped = self.client.post(self.apply_url, {"review_token": token})
        assert swapped.status_code == 302
        keep.refresh_from_db()
        replacement.refresh_from_db()
        assert keep.is_active is False
        assert replacement.is_active is True

    def test_f09_flag_off_and_flag_on_emptiness_are_independent(self) -> None:
        dynamic = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id="vendor/dynamic-only:free",
            display_name="Dynamic only",
            openrouter_managed=True,
            openrouter_available=True,
            model_type="language",
            tags=["tools"],
            is_active=True,
            released_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            sort_order=50,
        )
        overrides = {model.pk: (False, model.sort_order) for model in _all_rows()}
        overrides[dynamic.pk] = (True, dynamic.sort_order)
        token = self._review(overrides)
        refused = self.client.post(self.apply_url, {"review_token": token})
        assert refused.status_code == 409
        assert EMPTY_FLAG_OFF_MESSAGE.encode() in refused.content

        for provider, model_id in DIRECT_FREE_RIVAL_PAIRS:
            AIModel.objects.filter(provider=provider, model_id=model_id).update(is_active=False)
        AIModel.objects.filter(
            provider=NVIDIA_NIM_PROVIDER, model_id=NVIDIA_NIM_MODEL_ID
        ).update(is_active=False)
        AIModel.objects.filter(provider=OPENROUTER_PROVIDER).exclude(pk=dynamic.pk).update(
            openrouter_managed=False
        )
        bootstrap = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        bootstrap.is_active = True
        bootstrap.openrouter_available = True
        bootstrap.save()
        CatalogAdminControl.objects.filter(pk=1).update(revision=0)
        overrides = {model.pk: (model.is_active, model.sort_order) for model in _all_rows()}
        overrides[dynamic.pk] = (False, dynamic.sort_order)
        token = self._review(overrides)
        refused_on = self.client.post(self.apply_url, {"review_token": token})
        assert refused_on.status_code == 409
        assert EMPTY_FLAG_ON_MESSAGE.encode() in refused_on.content

        watchlist = AIModel.objects.get(model_id=WATCHLIST_FREE_RIVAL_PAIRS[0][1])
        overrides = {model.pk: (False, model.sort_order) for model in _all_rows()}
        overrides[watchlist.pk] = (True, watchlist.sort_order)
        token = self._review(overrides)
        refused_watch = self.client.post(self.apply_url, {"review_token": token})
        assert refused_watch.status_code == 409

    def test_f10_review_is_read_only_and_tokens_are_bound(self) -> None:
        target = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        before = target.sort_order
        overrides = {model.pk: (model.is_active, model.sort_order) for model in _all_rows()}
        overrides[target.pk] = (target.is_active, target.sort_order + 7)
        review = self.client.post(self.review_url, _formset(_all_rows(), overrides))
        target.refresh_from_db()
        assert target.sort_order == before
        token = _token(review.content.decode())
        applied = self.client.post(self.apply_url, {"review_token": token})
        assert applied.status_code == 302
        target.refresh_from_db()
        assert target.sort_order == before + 7
        assert LogEntry.objects.filter(object_id=str(target.pk)).exists()
        replay = self.client.post(self.apply_url, {"review_token": token})
        assert replay.status_code == 409
        assert STALE_REVIEW_MESSAGE.encode() in replay.content
        tampered = self.client.post(self.apply_url, {"review_token": token + "x"})
        assert tampered.status_code == 409
        fresh = sign_review_token(
            actor_id=self.user.pk,
            revision=CatalogAdminControl.objects.get(pk=1).revision,
            dynamic_enabled=False,
            changes=[
                CatalogChange(
                    model_id=target.pk,
                    is_active=target.is_active,
                    sort_order=target.sort_order,
                )
            ],
        )
        import time as time_module

        from catalog.admin_controls import load_review_token

        with patch(
            "django.core.signing.time.time",
            return_value=time_module.time() + 601,
        ):
            with self.assertRaises(CatalogControlError):
                load_review_token(fresh)

    def test_f02_apply_rejects_token_when_dynamic_flag_changes(self) -> None:
        target = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        before_order = target.sort_order
        before_active = target.is_active
        overrides = {model.pk: (model.is_active, model.sort_order) for model in _all_rows()}
        overrides[target.pk] = (target.is_active, target.sort_order + 3)

        false_token = self._review(overrides)
        with override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True):
            with self.assertRaises(CatalogControlError) as flipped_on:
                apply_reviewed_token(
                    token=false_token,
                    actor_id=self.user.pk,
                    has_row_change_permission=True,
                )
            assert flipped_on.exception.message == STALE_REVIEW_MESSAGE
            assert flipped_on.exception.status == 409
            refused_on = self.client.post(self.apply_url, {"review_token": false_token})
        assert refused_on.status_code == 409
        assert STALE_REVIEW_MESSAGE.encode() in refused_on.content
        target.refresh_from_db()
        assert target.sort_order == before_order
        assert target.is_active is before_active

        with override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True):
            true_token = self._review(overrides)
        with self.assertRaises(CatalogControlError) as flipped_off:
            apply_reviewed_token(
                token=true_token,
                actor_id=self.user.pk,
                has_row_change_permission=True,
            )
        assert flipped_off.exception.message == STALE_REVIEW_MESSAGE
        assert flipped_off.exception.status == 409
        refused_off = self.client.post(self.apply_url, {"review_token": true_token})
        assert refused_off.status_code == 409
        assert STALE_REVIEW_MESSAGE.encode() in refused_off.content
        target.refresh_from_db()
        assert target.sort_order == before_order
        assert target.is_active is before_active

    def test_f03_changeform_save_cannot_overwrite_reviewed_activation(self) -> None:
        model = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        tools_before = _active_tools_count()
        selectable_before = len(get_selectable_models())
        original_active = model.is_active
        original_order = model.sort_order
        concurrent_order = original_order + 17

        change_url = reverse("admin:catalog_aimodel_change", args=[model.pk])
        AIModel.objects.filter(pk=model.pk).update(sort_order=concurrent_order)
        posted = self.client.post(
            change_url,
            {
                "display_name": "Changeform metadata",
                "description": "updated via ordinary save",
                "quality_tier": model.quality_tier,
                "context_window": "" if model.context_window is None else str(model.context_window),
                "max_tokens": "" if model.max_tokens is None else str(model.max_tokens),
                "is_active": "off",
                "sort_order": str(original_order),
                "_save": "Save",
            },
        )
        assert posted.status_code in {200, 302}
        model.refresh_from_db()
        assert model.display_name == "Changeform metadata"
        assert model.description == "updated via ordinary save"
        assert model.is_active is original_active
        assert model.sort_order == concurrent_order
        assert _active_tools_count() == tools_before
        assert len(get_selectable_models()) == selectable_before

        stale = AIModel.objects.get(pk=model.pk)
        stale.display_name = "Stale changeform name"
        stale.description = "Stale changeform description"
        stale.is_active = False
        stale.sort_order = 0
        AIModel.objects.filter(pk=model.pk).update(sort_order=concurrent_order + 5)

        request = RequestFactory().post("/admin/")
        request.user = self.user
        admin = AIModelAdmin(AIModel, site)
        with patch.object(AIModel.objects, "get", return_value=stale):
            with CaptureQueriesContext(connection) as captured:
                admin.save_model(request, stale, form=None, change=True)

        model.refresh_from_db()
        assert model.display_name == "Stale changeform name"
        assert model.description == "Stale changeform description"
        assert model.is_active is original_active
        assert model.sort_order == concurrent_order + 5
        assert _active_tools_count() == tools_before
        assert len(get_selectable_models()) >= selectable_before
        update_sql = " ".join(
            query["sql"].lower()
            for query in captured.captured_queries
            if query["sql"].lstrip().lower().startswith("update")
        )
        assert "is_active" not in update_sql
        assert "sort_order" not in update_sql

    def test_f12_ordinary_admin_saves_cannot_bypass_review(self) -> None:
        model = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        original_active = model.is_active
        original_order = model.sort_order
        change_url = reverse("admin:catalog_aimodel_change", args=[model.pk])
        response = self.client.post(
            change_url,
            {
                "display_name": model.display_name,
                "description": model.description,
                "quality_tier": model.quality_tier,
                "is_active": "off",
                "sort_order": str(original_order + 50),
                "provider": "attacker",
                "model_id": "attacker/model",
                "_save": "Save",
            },
        )
        assert response.status_code in {200, 302}
        model.refresh_from_db()
        assert model.is_active is original_active
        assert model.sort_order == original_order
        assert model.provider == OPENROUTER_PROVIDER
        changelist = reverse("admin:catalog_aimodel_changelist")
        self.client.post(
            changelist,
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-0-id": str(model.pk),
                "form-0-is_active": "",
                "form-0-sort_order": "0",
                "_save": "Save",
            },
        )
        model.refresh_from_db()
        assert model.is_active is original_active
        delete = self.client.post(
            reverse("admin:catalog_aimodel_delete", args=[model.pk]),
            {"post": "yes"},
        )
        assert delete.status_code in {403, 302}
        assert AIModel.objects.filter(pk=model.pk).exists()

    def test_f13_methods_csrf_and_permissions(self) -> None:
        assert self.client.get(self.review_url).status_code == 405
        assert self.client.get(self.apply_url).status_code == 405
        probe_url = reverse(
            "admin:catalog_aimodel_probe",
            args=[AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1]).pk],
        )
        assert self.client.get(probe_url).status_code == 405
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        assert csrf.post(self.review_url, _formset(_all_rows())).status_code == 403
        anon = Client()
        assert anon.post(self.apply_url, {"review_token": "x"}).status_code == 302
        view_only = _staff("view_aimodel")
        viewer = Client()
        viewer.force_login(view_only)
        assert viewer.post(self.review_url, _formset(_all_rows())).status_code == 403
        assert viewer.post(probe_url, {"mode": "fake"}).status_code == 403
        assert self.client.get(self.controls_url).status_code == 200

    def test_f16_reviewed_priorities_reorder_direct_and_curated_only(self) -> None:
        groq = AIModel.objects.get(model_id=DIRECT_FREE_RIVAL_PAIRS[0][1])
        gemini = AIModel.objects.get(model_id=DIRECT_FREE_RIVAL_PAIRS[1][1])
        groq.is_active = True
        gemini.is_active = True
        groq.sort_order = 20
        gemini.sort_order = 1
        groq.save()
        gemini.save()
        gemma = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        other = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[3][1])
        gemma.sort_order = 80
        other.sort_order = 5
        gemma.save()
        other.save()
        token = self._review()
        applied = self.client.post(self.apply_url, {"review_token": token})
        assert applied.status_code == 302
        selected = get_selectable_models()
        assert selected[0].model_id == gemini.model_id
        assert selected[1].model_id == groq.model_id
        curated = [
            row.model_id
            for row in selected
            if (row.provider, row.model_id) in FREE_RIVAL_PAIRS
        ]
        assert curated[0] == other.model_id
        dynamic = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id="vendor/newer:free",
            display_name="Newer",
            openrouter_managed=True,
            openrouter_available=True,
            model_type="language",
            tags=["tools"],
            is_active=True,
            released_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            sort_order=0,
        )
        with override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True):
            flag_on = get_selectable_models()
        dynamic_ids = [
            row.model_id
            for row in flag_on
            if row.provider == OPENROUTER_PROVIDER
        ]
        assert dynamic.model_id in dynamic_ids
        assert flag_on[-1].model_id == NVIDIA_NIM_MODEL_ID
        assert flag_on[0].model_id == gemini.model_id

    def test_f17_seed_and_sync_preserve_operator_priority_and_activation(self) -> None:
        gemma = AIModel.objects.get(model_id=FREE_RIVAL_PAIRS[0][1])
        gemma.sort_order = 77
        gemma.is_active = False
        gemma.save(update_fields=["sort_order", "is_active"])
        before_revision = CatalogAdminControl.objects.get(pk=1).revision
        call_command("seed_models", stdout=StringIO())
        gemma.refresh_from_db()
        assert gemma.sort_order == 77
        assert gemma.is_active is False
        after_seed = CatalogAdminControl.objects.get(pk=1).revision
        assert after_seed > before_revision
        sync_openrouter_models(
            models=[
                OpenRouterModelRecord(
                    model_id=gemma.model_id,
                    display_name="Synced name",
                    description="synced",
                    model_type="language",
                    context_window=8192,
                    max_tokens=None,
                    tags=["tools"],
                    released_at=None,
                )
            ],
            allow_large_drop=True,
        )
        gemma.refresh_from_db()
        assert gemma.sort_order == 77
        assert gemma.is_active is False
        assert CatalogAdminControl.objects.get(pk=1).revision > after_seed


class CatalogAdminLockTests(TransactionTestCase):
    def test_f11_serialized_applies_cannot_drop_the_last_row(self) -> None:
        call_command("seed_models", stdout=StringIO())
        tools = [
            model
            for model in AIModel.objects.filter(model_type="language").order_by("id")
            if isinstance(model.tags, list) and "tools" in model.tags
        ]
        first, second = tools[0], tools[1]
        AIModel.objects.exclude(pk__in=[first.pk, second.pk]).update(is_active=False)
        first.is_active = True
        second.is_active = True
        first.save()
        second.save()
        control = CatalogAdminControl.objects.get(pk=1)
        fingerprint = catalog_fingerprint(revision=control.revision)
        user = User.objects.create_superuser("lock-admin", "a@b.c", "x")

        def deactivate(target: AIModel) -> None:
            apply_reviewed_changes(
                [
                    CatalogChange(
                        model_id=target.pk,
                        is_active=False,
                        sort_order=target.sort_order,
                    ),
                    CatalogChange(
                        model_id=first.pk if target.pk == second.pk else second.pk,
                        is_active=True,
                        sort_order=(
                            first.sort_order if target.pk == second.pk else second.sort_order
                        ),
                    ),
                ],
                actor_id=user.pk,
                expected_revision=control.revision,
                expected_fingerprint=fingerprint,
                has_row_change_permission=True,
            )

        deactivate(first)
        from catalog.admin_controls import CatalogControlError

        try:
            deactivate(second)
            raised = False
        except CatalogControlError:
            raised = True
        assert raised is True
        remaining = [
            model
            for model in AIModel.objects.filter(is_active=True, model_type="language")
            if isinstance(model.tags, list) and "tools" in model.tags
        ]
        assert len(remaining) >= 1
