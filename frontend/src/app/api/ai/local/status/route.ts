import { NextRequest, NextResponse } from "next/server";
import {
  DEFAULT_LOCAL_AI_MODEL_ID,
  stripLocalAIModelPrefix,
} from "@/lib/local-ai";
import {
  fetchLMStudioModelCatalog,
  getLMStudioBaseUrl,
  getLMStudioApiV0BaseUrl,
  modelMatches,
  selectLoadedLMStudioModel,
} from "@/lib/lm-studio";

export async function GET(req: NextRequest) {
  const requestedModelId = stripLocalAIModelPrefix(
    req.nextUrl.searchParams.get("model") || DEFAULT_LOCAL_AI_MODEL_ID,
  );
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2500);

  try {
    const models = await fetchLMStudioModelCatalog(controller.signal);
    const loadedModel = selectLoadedLMStudioModel(
      models,
      req.nextUrl.searchParams.get("model") || DEFAULT_LOCAL_AI_MODEL_ID,
    );
    const loadedModelIds = models
      .filter((model) => model.state === "loaded")
      .map((model) => model.id);

    return NextResponse.json({
      ok: true,
      reachable: true,
      base_url: getLMStudioBaseUrl(),
      api_base_url: getLMStudioApiV0BaseUrl(),
      model_id: requestedModelId,
      runtime_model_id: loadedModel?.id ?? null,
      matching_model_loaded: loadedModelIds.some((modelId) =>
        modelMatches(modelId, requestedModelId),
      ),
      models: loadedModelIds.slice(0, 12),
      available_models: models.map((model) => ({
        id: model.id,
        state: model.state,
        type: model.type,
        capabilities: model.capabilities,
      })),
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      reachable: false,
      base_url: getLMStudioBaseUrl(),
      api_base_url: getLMStudioApiV0BaseUrl(),
      model_id: requestedModelId,
      runtime_model_id: null,
      matching_model_loaded: false,
      models: [],
      available_models: [],
      error: error instanceof Error ? error.message : "LM Studio is unreachable.",
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
