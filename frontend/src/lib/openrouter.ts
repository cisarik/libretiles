/**
 * OpenRouter Chat Completions client.
 *
 * Uses `@ai-sdk/openai` as an OpenAI-compatible adapter against
 * https://openrouter.ai/api/v1. `.chat()` keeps tool calling on
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

const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";

export function isOpenRouterConfigured(): boolean {
  try {
    requireServerCredential(process.env.OPENROUTER_API_KEY);
    return true;
  } catch {
    return false;
  }
}

export function createOpenRouterProvider(
  tracker: ProviderRequestTracker = createProviderRequestTracker(),
) {
  return createOpenAI({
    baseURL: OPENROUTER_BASE_URL,
    apiKey: requireServerCredential(process.env.OPENROUTER_API_KEY),
    name: "openrouter",
    fetch: createTrackedProviderFetch(tracker),
  });
}

/**
 * LanguageModel for Chat Completions. Throws a clear auth error when
 * the OpenRouter key is missing; never falls back to other vendor keys.
 */
export function getOpenRouterModel(
  modelId: string,
  tracker: ProviderRequestTracker,
): LanguageModel {
  return createOpenRouterProvider(tracker).chat(modelId);
}
