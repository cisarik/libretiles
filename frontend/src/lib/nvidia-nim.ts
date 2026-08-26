/**
 * NVIDIA NIM Chat Completions client.
 *
 * Uses `@ai-sdk/openai` as an OpenAI-compatible adapter against
 * https://integrate.api.nvidia.com/v1. `.chat()` keeps tool calling on
 * Chat Completions, not the Responses API.
 */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import {
  createProviderRequestTracker,
  createTrackedProviderFetch,
  requireServerCredential,
  type ProviderRequestTracker,
} from "./openai-compatible";

const NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1";

export function isNvidiaNimConfigured(): boolean {
  try {
    requireServerCredential(process.env.NVIDIA_API_KEY);
    return true;
  } catch {
    return false;
  }
}

export function createNvidiaNimProvider(
  tracker: ProviderRequestTracker = createProviderRequestTracker(),
) {
  return createOpenAI({
    baseURL: NVIDIA_NIM_BASE_URL,
    apiKey: requireServerCredential(process.env.NVIDIA_API_KEY),
    name: "nvidia-nim",
    fetch: createTrackedProviderFetch(tracker),
  });
}

/**
 * LanguageModel for Chat Completions. Throws a sanitised auth error when
 * the NVIDIA key is missing; never interpolates the key value.
 */
export function getNvidiaNimModel(
  modelId: string,
  tracker: ProviderRequestTracker,
): LanguageModel {
  return createNvidiaNimProvider(tracker).chat(modelId);
}
