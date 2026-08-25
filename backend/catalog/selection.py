from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone as django_timezone

from .models import AIModel, AIPrompt

# Keep these strings in sync with frontend/src/lib/free-rivals.ts.
DEFAULT_FREE_MODEL_ID = "google/gemma-4-31b-it:free"
OPENROUTER_PROVIDER = "openrouter"
NVIDIA_NIM_PROVIDER = "nvidia-nim"
NVIDIA_NIM_MODEL_ID = "nvidia/nemotron-3-super-120b-a12b"
FREE_RIVAL_PAIRS: tuple[tuple[str, str], ...] = (
    (OPENROUTER_PROVIDER, DEFAULT_FREE_MODEL_ID),
    (NVIDIA_NIM_PROVIDER, NVIDIA_NIM_MODEL_ID),
    (OPENROUTER_PROVIDER, "nvidia/nemotron-3-super-120b-a12b:free"),
    (OPENROUTER_PROVIDER, "z-ai/glm-5.2:free"),
    (OPENROUTER_PROVIDER, "google/gemma-4-26b-a4b-it:free"),
)
FREE_RIVAL_IDS: tuple[str, ...] = tuple(model_id for _, model_id in FREE_RIVAL_PAIRS)
OPENROUTER_SHORTLIST_IDS: frozenset[str] = frozenset(
    model_id for provider, model_id in FREE_RIVAL_PAIRS if provider == OPENROUTER_PROVIDER
)
SHORTLIST_SORT_ORDER = {
    model_id: (index + 1) * 10 for index, (_, model_id) in enumerate(FREE_RIVAL_PAIRS)
}
TOOLS_TAG = "tools"
EXCLUDED_MODEL_IDS = frozenset({"openrouter/free"})
OPENROUTER_COHORT_SIZE = 4
MAX_FUTURE_RELEASE_SKEW = timedelta(hours=24)
_NON_BOOTSTRAP_SORT_ORDER = 10**9


def _dynamic_catalog_enabled() -> bool:
    return bool(getattr(settings, "DYNAMIC_FREE_MODEL_CATALOG_ENABLED", False))


def get_selectable_models() -> list[AIModel]:
    rows = {
        (model.provider, model.model_id): model
        for model in AIModel.objects.filter(
            is_active=True,
            model_type="language",
        )
    }
    if _dynamic_catalog_enabled():
        return _dynamic_selectable(rows)
    return _bootstrap_selectable(rows)


def _bootstrap_selectable(rows: dict[tuple[str, str], AIModel]) -> list[AIModel]:
    selected: list[AIModel] = []
    for provider, model_id in FREE_RIVAL_PAIRS:
        model = rows.get((provider, model_id))
        if model is None:
            continue
        if provider == OPENROUTER_PROVIDER and not model.openrouter_available:
            continue
        if not _has_tools_tag(model):
            continue
        selected.append(model)
    return selected


def _dynamic_selectable(rows: dict[tuple[str, str], AIModel]) -> list[AIModel]:
    openrouter_models = [
        model
        for (provider, _model_id), model in rows.items()
        if provider == OPENROUTER_PROVIDER and _is_dynamic_openrouter_candidate(model)
    ]
    openrouter_models.sort(key=_newest_first_key)
    selected = openrouter_models[:OPENROUTER_COHORT_SIZE]
    nim = rows.get((NVIDIA_NIM_PROVIDER, NVIDIA_NIM_MODEL_ID))
    if nim is not None and _has_tools_tag(nim):
        selected.append(nim)
    return selected


def _is_dynamic_openrouter_candidate(model: AIModel) -> bool:
    if not model.openrouter_managed or not model.openrouter_available:
        return False
    if model.model_id in EXCLUDED_MODEL_IDS:
        return False
    if "/" not in model.model_id or not model.model_id.endswith(":free"):
        return False
    return _has_tools_tag(model)


def _usable_released_at(model: AIModel) -> datetime | None:
    released = model.released_at
    if released is None:
        return None
    if released > django_timezone.now() + MAX_FUTURE_RELEASE_SKEW:
        return None
    return released


def _newest_first_key(model: AIModel) -> tuple[int, float, int, str]:
    released = _usable_released_at(model)
    missing = 1 if released is None else 0
    descending = -released.timestamp() if released is not None else 0.0
    bootstrap = SHORTLIST_SORT_ORDER.get(model.model_id, _NON_BOOTSTRAP_SORT_ORDER)
    return (missing, descending, bootstrap, model.model_id)


def is_selectable_model(model_id: str) -> bool:
    return any(model.model_id == model_id for model in get_selectable_models())


def get_selectable_prompts() -> list[AIPrompt]:
    return list(AIPrompt.objects.filter(is_active=True).order_by("sort_order", "name"))


def is_selectable_prompt(prompt_id: int) -> bool:
    return any(prompt.id == prompt_id for prompt in get_selectable_prompts())


def is_curated_free_rival(model: AIModel) -> bool:
    return (model.provider, model.model_id) in FREE_RIVAL_PAIRS


def _has_tools_tag(model: AIModel) -> bool:
    tags = model.tags if isinstance(model.tags, list) else []
    return TOOLS_TAG in tags
