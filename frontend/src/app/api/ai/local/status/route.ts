import { NextRequest, NextResponse } from "next/server";
import {
  DEFAULT_LOCAL_AI_MODEL_ID,
  stripLocalAIModelPrefix,
} from "@/lib/local-ai";

const LM_STUDIO_BASE_URL =
  process.env.LM_STUDIO_BASE_URL || "http://localhost:1234/v1";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function modelMatches(loadedModelId: string, requestedModelId: string): boolean {
  const loaded = loadedModelId.toLowerCase();
  const requested = requestedModelId.toLowerCase();
  return (
    loaded === requested ||
    loaded.endsWith(`/${requested}`) ||
    loaded.includes(requested)
  );
}

export async function GET(req: NextRequest) {
  const requestedModelId = stripLocalAIModelPrefix(
    req.nextUrl.searchParams.get("model") || DEFAULT_LOCAL_AI_MODEL_ID,
  );
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2500);

  try {
    const res = await fetch(`${trimTrailingSlash(LM_STUDIO_BASE_URL)}/models`, {
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = await res.json().catch(() => null);
    const rawModels = Array.isArray(payload?.data) ? payload.data : [];
    const modelIds: string[] = rawModels
      .map((model: unknown) =>
        typeof model === "object" &&
        model !== null &&
        "id" in model &&
        typeof model.id === "string"
          ? model.id
          : null,
      )
      .filter((modelId: string | null): modelId is string => modelId !== null);

    return NextResponse.json({
      ok: res.ok,
      reachable: res.ok,
      base_url: LM_STUDIO_BASE_URL,
      model_id: requestedModelId,
      matching_model_loaded: modelIds.some((modelId) =>
        modelMatches(modelId, requestedModelId),
      ),
      models: modelIds.slice(0, 12),
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      reachable: false,
      base_url: LM_STUDIO_BASE_URL,
      model_id: requestedModelId,
      matching_model_loaded: false,
      models: [],
      error: error instanceof Error ? error.message : "LM Studio is unreachable.",
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
