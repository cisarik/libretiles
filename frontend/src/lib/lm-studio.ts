import { isLocalAIAutoModelId, stripLocalAIModelPrefix } from "@/lib/local-ai";

export type LMStudioModelInfo = {
  id: string;
  state: string;
  type: string;
  capabilities: string[];
  max_context_length?: number;
};

const LM_STUDIO_BASE_URL =
  process.env.LM_STUDIO_BASE_URL || "http://localhost:1234/v1";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getLMStudioBaseUrl(): string {
  return LM_STUDIO_BASE_URL;
}

export function getLMStudioApiV0BaseUrl(): string {
  const baseUrl = trimTrailingSlash(LM_STUDIO_BASE_URL);
  if (baseUrl.endsWith("/v1")) {
    return `${baseUrl.slice(0, -3)}/api/v0`;
  }
  return `${baseUrl}/api/v0`;
}

export function modelMatches(
  loadedModelId: string,
  requestedModelId: string,
): boolean {
  const loaded = loadedModelId.toLowerCase();
  const requested = requestedModelId.toLowerCase();
  return (
    loaded === requested ||
    loaded.endsWith(`/${requested}`) ||
    loaded.includes(requested)
  );
}

export function isUsableLMStudioChatModel(model: LMStudioModelInfo): boolean {
  const type = model.type.toLowerCase();
  return (
    (type === "llm" || type === "vlm") &&
    model.state === "loaded" &&
    model.capabilities.includes("tool_use")
  );
}

export async function fetchLMStudioModelCatalog(
  signal?: AbortSignal,
): Promise<LMStudioModelInfo[]> {
  const res = await fetch(`${getLMStudioApiV0BaseUrl()}/models`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    throw new Error(`LM Studio models endpoint returned ${res.status}`);
  }

  const payload = await res.json().catch(() => null);
  const rawModels: unknown[] = Array.isArray(payload?.data) ? payload.data : [];
  return rawModels
    .map((model: unknown): LMStudioModelInfo | null => {
      if (typeof model !== "object" || model === null || !("id" in model)) {
        return null;
      }
      const candidate = model as {
        id?: unknown;
        state?: unknown;
        type?: unknown;
        capabilities?: unknown;
        max_context_length?: unknown;
      };
      if (typeof candidate.id !== "string") return null;
      return {
        id: candidate.id,
        state: typeof candidate.state === "string" ? candidate.state : "unknown",
        type: typeof candidate.type === "string" ? candidate.type : "unknown",
        capabilities: Array.isArray(candidate.capabilities)
          ? candidate.capabilities.filter(
              (capability): capability is string => typeof capability === "string",
            )
          : [],
        max_context_length:
          typeof candidate.max_context_length === "number"
            ? candidate.max_context_length
            : undefined,
      };
    })
    .filter((model): model is LMStudioModelInfo => model !== null);
}

export function selectLoadedLMStudioModel(
  models: LMStudioModelInfo[],
  preferredModelId?: string | null,
): LMStudioModelInfo | null {
  const preferred = preferredModelId
    ? stripLocalAIModelPrefix(preferredModelId)
    : null;
  const usableModels = models.filter(isUsableLMStudioChatModel);

  if (preferred && !isLocalAIAutoModelId(preferredModelId)) {
    const exact = usableModels.find((model) => modelMatches(model.id, preferred));
    if (exact) return exact;
  }

  return usableModels[0] ?? null;
}

export async function resolveLMStudioRuntimeModelId(
  catalogModelId: string,
): Promise<string | null> {
  const models = await fetchLMStudioModelCatalog();
  const selected = selectLoadedLMStudioModel(models, catalogModelId);
  if (selected) return selected.id;

  if (!isLocalAIAutoModelId(catalogModelId)) {
    return stripLocalAIModelPrefix(catalogModelId);
  }

  return null;
}
