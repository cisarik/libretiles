import { isLocalAIAutoModelId, stripLocalAIModelPrefix } from "@/lib/local-ai";

export type LMStudioModelInfo = {
  id: string;
  state: string;
  type: string;
  capabilities: string[];
  max_context_length?: number;
  loaded_context_length?: number | null;
};

const LM_STUDIO_BASE_URL =
  process.env.LM_STUDIO_BASE_URL || "http://localhost:1234/v1";
const LM_STUDIO_API_KEY = process.env.LM_STUDIO_API_KEY || "lm-studio";

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

export function getLMStudioApiV1BaseUrl(): string {
  const baseUrl = trimTrailingSlash(LM_STUDIO_BASE_URL);
  if (baseUrl.endsWith("/v1")) {
    return `${baseUrl.slice(0, -3)}/api/v1`;
  }
  return `${baseUrl}/api/v1`;
}

function getLMStudioRequestHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${LM_STUDIO_API_KEY}`,
  };
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
  return isLMStudioChatModel(model) && model.state === "loaded";
}

export function isLMStudioChatModel(model: LMStudioModelInfo): boolean {
  const type = model.type.toLowerCase();
  return (
    (type === "llm" || type === "vlm") &&
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
        loaded_context_length?: unknown;
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
        loaded_context_length:
          typeof candidate.loaded_context_length === "number"
            ? candidate.loaded_context_length
            : null,
      };
    })
    .filter((model): model is LMStudioModelInfo => model !== null);
}

export function selectLoadedLMStudioModel(
  models: LMStudioModelInfo[],
  preferredModelId?: string | null,
): LMStudioModelInfo | null {
  return selectLMStudioModel(models, preferredModelId, { requireLoaded: true });
}

export function selectLMStudioModel(
  models: LMStudioModelInfo[],
  preferredModelId?: string | null,
  options: { requireLoaded?: boolean } = {},
): LMStudioModelInfo | null {
  const preferred = preferredModelId
    ? stripLocalAIModelPrefix(preferredModelId)
    : null;
  const usableModels = models.filter((model) =>
    options.requireLoaded ? isUsableLMStudioChatModel(model) : isLMStudioChatModel(model),
  );

  if (preferred && !isLocalAIAutoModelId(preferredModelId)) {
    const exact = usableModels.find((model) => modelMatches(model.id, preferred));
    if (exact) return exact;
  }

  return usableModels[0] ?? null;
}

export async function resolveLMStudioRuntimeModelId(
  catalogModelId: string,
  options: { allowUnloaded?: boolean } = {},
): Promise<string | null> {
  const models = await fetchLMStudioModelCatalog();
  const selected = options.allowUnloaded
    ? selectLMStudioModel(models, catalogModelId)
    : selectLoadedLMStudioModel(models, catalogModelId);
  if (selected) return selected.id;

  if (!isLocalAIAutoModelId(catalogModelId)) {
    return stripLocalAIModelPrefix(catalogModelId);
  }

  return null;
}

export async function loadLMStudioModel({
  modelId,
  contextLength,
  signal,
}: {
  modelId: string;
  contextLength: number;
  signal?: AbortSignal;
}): Promise<Record<string, unknown>> {
  const res = await fetch(`${getLMStudioApiV1BaseUrl()}/models/load`, {
    method: "POST",
    cache: "no-store",
    headers: getLMStudioRequestHeaders(),
    body: JSON.stringify({
      model: modelId,
      context_length: contextLength,
      echo_load_config: true,
    }),
    signal,
  });

  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      typeof payload?.error === "string"
        ? payload.error
        : `LM Studio load endpoint returned ${res.status}`;
    throw new Error(message);
  }

  return isRecord(payload) ? payload : {};
}

export async function unloadLMStudioModel(
  instanceId: string,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${getLMStudioApiV1BaseUrl()}/models/unload`, {
    method: "POST",
    cache: "no-store",
    headers: getLMStudioRequestHeaders(),
    body: JSON.stringify({ instance_id: instanceId }),
    signal,
  });

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    const message =
      typeof payload?.error === "string"
        ? payload.error
        : `LM Studio unload endpoint returned ${res.status}`;
    throw new Error(message);
  }
}

export async function prepareLMStudioModelForTurn({
  catalogModelId,
  contextLength,
  reloadBeforeTurn,
  signal,
}: {
  catalogModelId: string;
  contextLength: number;
  reloadBeforeTurn: boolean;
  signal?: AbortSignal;
}): Promise<{
  runtimeModelId: string;
  instanceId: string;
  loadedBeforePrepare: boolean;
  loadedContextLength: number | null;
  requestedContextLength: number;
  effectiveContextLength: number;
  modelMaxContextLength: number | null;
  contextClamped: boolean;
  loadResult: Record<string, unknown> | null;
}> {
  const models = await fetchLMStudioModelCatalog(signal);
  const selected =
    selectLoadedLMStudioModel(models, catalogModelId) ??
    selectLMStudioModel(models, catalogModelId);

  if (!selected) {
    if (!isLocalAIAutoModelId(catalogModelId)) {
      const runtimeModelId = stripLocalAIModelPrefix(catalogModelId);
      const loadResult = await loadLMStudioModel({
        modelId: runtimeModelId,
        contextLength,
        signal,
      });
      return {
        runtimeModelId,
        instanceId: getLMStudioInstanceId(loadResult, runtimeModelId),
        loadedBeforePrepare: false,
        loadedContextLength: null,
        requestedContextLength: contextLength,
        effectiveContextLength: contextLength,
        modelMaxContextLength: null,
        contextClamped: false,
        loadResult,
      };
    }

    throw new Error(
      "No LM Studio chat model is available. Download a tool-capable LLM/VLM in LM Studio first.",
    );
  }

  // Clamp the requested context window to what the model actually supports so a
  // user-configured value that exceeds the model's max never fails the load.
  const modelMaxContextLength =
    typeof selected.max_context_length === "number" &&
    selected.max_context_length > 0
      ? selected.max_context_length
      : null;
  const effectiveContextLength = modelMaxContextLength
    ? Math.min(contextLength, modelMaxContextLength)
    : contextLength;
  const contextClamped = effectiveContextLength !== contextLength;

  const loadedBeforePrepare = selected.state === "loaded";
  const loadedContextLength = selected.loaded_context_length ?? null;
  const needsLoad =
    reloadBeforeTurn ||
    !loadedBeforePrepare ||
    loadedContextLength !== effectiveContextLength;

  if (loadedBeforePrepare && needsLoad) {
    await unloadLMStudioModel(selected.id, signal).catch((error) => {
      if (error instanceof Error && error.message.toLowerCase().includes("not loaded")) {
        return;
      }
      throw error;
    });
  }

  const loadResult = needsLoad
    ? await loadLMStudioModel({
        modelId: selected.id,
        contextLength: effectiveContextLength,
        signal,
      })
    : null;

  return {
    runtimeModelId: selected.id,
    instanceId: getLMStudioInstanceId(loadResult, selected.id),
    loadedBeforePrepare,
    loadedContextLength,
    requestedContextLength: contextLength,
    effectiveContextLength,
    modelMaxContextLength,
    contextClamped,
    loadResult,
  };
}

function getLMStudioInstanceId(
  loadResult: Record<string, unknown> | null,
  fallback: string,
): string {
  return typeof loadResult?.instance_id === "string"
    ? loadResult.instance_id
    : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
