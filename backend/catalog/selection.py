from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .models import AIModel, AIPrompt

PINNED_MODEL_ID = "openai/gpt-5.4"
DEFAULT_SELECTABLE_MODEL_LIMIT = 20
LOCAL_MODEL_PROVIDER = "lmstudio"
LOCAL_MODEL_PREFIX = f"{LOCAL_MODEL_PROVIDER}/"
LOCAL_AUTO_MODEL_ID = f"{LOCAL_MODEL_PREFIX}auto"
_ZERO = Decimal("0")
_MILLION = Decimal("1000000")


def get_selectable_models(
    *,
    limit: int = DEFAULT_SELECTABLE_MODEL_LIMIT,
    pinned_model_id: str = PINNED_MODEL_ID,
) -> list[AIModel]:
    models = list(AIModel.objects.filter(is_active=True, model_type="language"))
    if models:
        synced_models = [
            model for model in models if model.gateway_available or is_local_model(model)
        ]
        if synced_models:
            models = synced_models

        tool_capable_models = [model for model in models if is_tool_capable_model(model)]
        non_local_tool_capable_models = [
            model for model in tool_capable_models if not is_local_model(model)
        ]
        if non_local_tool_capable_models:
            local_models = [model for model in models if is_local_model(model)]
            non_local_tool_model_ids = {
                model.id for model in non_local_tool_capable_models
            }
            models = [
                *non_local_tool_capable_models,
                *[
                    model
                    for model in local_models
                    if model.id not in non_local_tool_model_ids
                ],
            ]

    sorted_models = sorted(models, key=_selectable_model_sort_key, reverse=True)

    if limit <= 0:
        return sorted_models

    top_models = sorted_models[:limit]
    required_models = [model for model in sorted_models if is_local_model(model)]

    pinned = AIModel.objects.filter(
        model_id=pinned_model_id,
        gateway_available=True,
        model_type="language",
    ).first()
    if pinned is not None and not (
        models and any(is_tool_capable_model(model) for model in models) and not is_tool_capable_model(pinned)
    ):
        required_models.append(pinned)

    return _with_required_models(top_models=top_models, required_models=required_models, limit=limit)


def is_selectable_model(model_id: str) -> bool:
    if is_local_model_id(model_id):
        return True
    return any(model.model_id == model_id for model in get_selectable_models())


def get_selectable_prompts() -> list[AIPrompt]:
    return list(AIPrompt.objects.filter(is_active=True).order_by("sort_order", "name"))


def is_selectable_prompt(prompt_id: int) -> bool:
    return any(prompt.id == prompt_id for prompt in get_selectable_prompts())


def is_tool_capable_model(model: AIModel) -> bool:
    tags = model.tags if isinstance(model.tags, list) else []
    return bool("tool-use" in tags)


def is_local_model(model: AIModel) -> bool:
    return is_local_model_id(model.model_id) or model.provider == LOCAL_MODEL_PROVIDER


def is_local_model_id(model_id: str | None) -> bool:
    if not model_id:
        return False
    return bool(
        model_id.startswith(LOCAL_MODEL_PREFIX)
        and len(model_id) > len(LOCAL_MODEL_PREFIX)
    )


def ensure_local_ai_model(model_id: str) -> AIModel:
    runtime_id = model_id.removeprefix(LOCAL_MODEL_PREFIX)
    display_name = (
        "LM Studio Auto"
        if model_id == LOCAL_AUTO_MODEL_ID
        else f"{_humanize_local_model_id(runtime_id)} (LM Studio)"
    )
    description = (
        "Local offline opponent loaded by LM Studio for each AI turn. "
        "Charges no credits."
    )
    model, _created = AIModel.objects.get_or_create(
        model_id=model_id,
        defaults={
            "provider": LOCAL_MODEL_PROVIDER,
            "display_name": display_name,
            "description": description,
            "quality_tier": "standard",
            "cost_per_game": "0.00",
            "gateway_managed": False,
            "gateway_available": True,
            "model_type": "language",
            "context_window": 32768,
            "tags": ["tool-use"],
            "pricing": {},
            "sort_order": 1,
        },
    )
    return model


def _humanize_local_model_id(model_id: str) -> str:
    tail = model_id.split("/")[-1]
    parts = [part for part in tail.replace("_", "-").split("-") if part]
    normalized: list[str] = []
    for part in parts:
        if part.isdigit() or any(char.isdigit() for char in part):
            normalized.append(part.upper())
        elif len(part) <= 3:
            normalized.append(part.upper())
        else:
            normalized.append(part[:1].upper() + part[1:])
    return " ".join(normalized) or model_id


def _selectable_model_sort_key(model: AIModel) -> tuple[Decimal, Decimal, Decimal, str]:
    return (
        get_combined_cost_per_token(model),
        get_output_cost_per_token(model),
        get_input_cost_per_token(model),
        model.display_name.lower(),
    )


def _with_required_models(
    *,
    top_models: list[AIModel],
    required_models: list[AIModel],
    limit: int,
) -> list[AIModel]:
    selected = list(top_models)
    required_ids = {model.id for model in required_models}

    for required in required_models:
        if any(model.id == required.id for model in selected):
            continue
        if len(selected) >= limit:
            replace_index = next(
                (
                    index
                    for index in range(len(selected) - 1, -1, -1)
                    if selected[index].id not in required_ids
                ),
                len(selected) - 1,
            )
            selected.pop(replace_index)
        selected.append(required)

    return sorted(selected, key=_selectable_model_sort_key, reverse=True)


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
