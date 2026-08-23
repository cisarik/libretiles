from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import AIModel, AIPrompt

# Keep these strings in sync with frontend/src/lib/free-rivals.ts.
DEFAULT_FREE_MODEL_ID = "google/gemma-4-31b-it:free"
FREE_RIVAL_IDS: tuple[str, ...] = (
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "z-ai/glm-5.2:free",
    "google/gemma-4-26b-a4b-it:free",
)
SHORTLIST_SORT_ORDER = {
    model_id: (index + 1) * 10 for index, model_id in enumerate(FREE_RIVAL_IDS)
}
TOOLS_TAG = "tools"
_ZERO = Decimal("0")
_MILLION = Decimal("1000000")


def get_selectable_models() -> list[AIModel]:
    rows = {
        model.model_id: model
        for model in AIModel.objects.filter(
            is_active=True,
            openrouter_available=True,
            provider="openrouter",
            model_type="language",
        )
    }
    selected: list[AIModel] = []
    for model_id in FREE_RIVAL_IDS:
        model = rows.get(model_id)
        if model is None:
            continue
        if not _has_tools_tag(model):
            continue
        if not is_explicitly_free(model):
            continue
        selected.append(model)
    return selected


def is_selectable_model(model_id: str) -> bool:
    return any(model.model_id == model_id for model in get_selectable_models())


def get_selectable_prompts() -> list[AIPrompt]:
    return list(AIPrompt.objects.filter(is_active=True).order_by("sort_order", "name"))


def is_selectable_prompt(prompt_id: int) -> bool:
    return any(prompt.id == prompt_id for prompt in get_selectable_prompts())


def is_explicitly_free(model: AIModel) -> bool:
    if _as_decimal(model.cost_per_game) != _ZERO:
        return False
    pricing = model.pricing if isinstance(model.pricing, dict) else {}
    for key in ("input", "output"):
        if key not in pricing or pricing.get(key) in (None, ""):
            continue
        if _as_decimal(pricing.get(key)) != _ZERO:
            return False
    return True


def get_input_cost_per_token(model: AIModel) -> Decimal:
    return _pricing_decimal(model, "input")


def get_output_cost_per_token(model: AIModel) -> Decimal:
    return _pricing_decimal(model, "output")


def get_cache_read_cost_per_token(model: AIModel) -> Decimal:
    return _pricing_decimal(model, "input_cache_read")


def get_cache_write_cost_per_token(model: AIModel) -> Decimal:
    return _pricing_decimal(model, "input_cache_write")


def get_combined_cost_per_token(model: AIModel) -> Decimal:
    return get_input_cost_per_token(model) + get_output_cost_per_token(model)


def get_combined_cost_per_million(model: AIModel) -> Decimal:
    return get_combined_cost_per_token(model) * _MILLION


def _has_tools_tag(model: AIModel) -> bool:
    tags = model.tags if isinstance(model.tags, list) else []
    return TOOLS_TAG in tags


def _pricing_decimal(model: AIModel, key: str) -> Decimal:
    pricing = model.pricing if isinstance(model.pricing, dict) else {}
    return _as_decimal(pricing.get(key))


def _as_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return _ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO
