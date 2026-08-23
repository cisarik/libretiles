/**
 * OpenRouter Chat Completions client.
 *
 * Uses `@ai-sdk/openai` as an OpenAI-compatible adapter against
 * https://openrouter.ai/api/v1. `.chat()` keeps tool calling on
 * Chat Completions, not the Responses API.
 */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";

const OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1";

export function isOpenRouterConfigured(): boolean {
  return Boolean(process.env.OPENROUTER_API_KEY);
}

export function createOpenRouterProvider() {
  return createOpenAI({
    baseURL: OPENROUTER_BASE_URL,
    apiKey: process.env.OPENROUTER_API_KEY,
    name: "openrouter",
  });
}

/**
 * LanguageModel for Chat Completions. Throws a clear auth error when
 * the OpenRouter key is missing; never falls back to other vendor keys.
 */
export function getOpenRouterModel(modelId: string): LanguageModel {
  if (!isOpenRouterConfigured()) {
    throw new Error(
      "OpenRouter authentication failed: missing or invalid API key",
    );
  }

  return createOpenRouterProvider().chat(modelId);
}
