export const LOCAL_AI_PROVIDER = "lmstudio";
export const LOCAL_AI_MODEL_PREFIX = `${LOCAL_AI_PROVIDER}/`;
export const LOCAL_AI_AUTO_MODEL_ID = `${LOCAL_AI_MODEL_PREFIX}auto`;
export const DEFAULT_LOCAL_AI_MODEL_ID = LOCAL_AI_AUTO_MODEL_ID;
export const DEFAULT_LOCAL_AI_FALLBACK_MODEL_ID = `${LOCAL_AI_MODEL_PREFIX}qwen3-14b-sk`;

export function isLocalAIModelId(modelId?: string | null): boolean {
  return modelId?.toLowerCase().startsWith(LOCAL_AI_MODEL_PREFIX) === true;
}

export function stripLocalAIModelPrefix(modelId: string): string {
  if (!isLocalAIModelId(modelId)) return modelId;
  return modelId.slice(LOCAL_AI_MODEL_PREFIX.length);
}

export function isLocalAIAutoModelId(modelId?: string | null): boolean {
  return modelId?.toLowerCase() === LOCAL_AI_AUTO_MODEL_ID;
}
