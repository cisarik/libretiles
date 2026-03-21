from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import AIModel

PINNED_MODEL_ID = "openai/gpt-5.4"
DEFAULT_SELECTABLE_MODEL_LIMIT = 20
_ZERO = Decimal("0")
_MILLION = Decimal("1000000")


def get_selectable_models(
    *,
    limit: int = DEFAULT_SELECTABLE_MODEL_LIMIT,
    pinned_model_id: str = PINNED_MODEL_ID,
) -> list[AIModel]:
    models = list(AIModel.objects.filter(is_active=True, model_type="language"))
    if models:
        synced_models = [model for model in models if model.gateway_available]
        if synced_models:
            models = synced_models

        tool_capable_models = [model for model in models if is_tool_capable_model(model)]
        if tool_capable_models:
            models = tool_capable_models

    sorted_models = sorted(
        models,
        key=lambda model: (
            get_combined_cost_per_token(model),
            get_output_cost_per_token(model),
            get_input_cost_per_token(model),
            model.display_name.lower(),
        ),
        reverse=True,
    )

    if limit <= 0:
        return sorted_models

    top_models = sorted_models[:limit]
    if any(model.model_id == pinned_model_id for model in top_models):
        return top_models

    pinned = AIModel.objects.filter(
        model_id=pinned_model_id,
        gateway_available=True,
        model_type="language",
    ).first()
    if pinned is None:
        return top_models
    if models and any(is_tool_capable_model(model) for model in models) and not is_tool_capable_model(pinned):
        return top_models

    with_pinned = [
        *[model for model in top_models if model.model_id != pinned_model_id][: limit - 1],
        pinned,
    ]
    return sorted(
        with_pinned,
        key=lambda model: (
            get_combined_cost_per_token(model),
            get_output_cost_per_token(model),
            get_input_cost_per_token(model),
            model.display_name.lower(),
        ),
        reverse=True,
    )


def is_selectable_model(model_id: str) -> bool:
    return any(model.model_id == model_id for model in get_selectable_models())


def is_tool_capable_model(model: AIModel) -> bool:
    tags = model.tags if isinstance(model.tags, list) else []
    return "tool-use" in tags


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


def _pricing_decimal(model: AIModel, key: str) -> Decimal:
    pricing = model.pricing if isinstance(model.pricing, dict) else {}
    raw_value = pricing.get(key)
    if raw_value is None:
        return _ZERO
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO
