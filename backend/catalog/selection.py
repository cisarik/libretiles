from __future__ import annotations

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


def get_selectable_models() -> list[AIModel]:
    rows = {
        (model.provider, model.model_id): model
        for model in AIModel.objects.filter(
            is_active=True,
            model_type="language",
        )
    }
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
