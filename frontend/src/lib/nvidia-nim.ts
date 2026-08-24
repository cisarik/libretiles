/**
 * NVIDIA NIM Chat Completions client.
 *
 * Uses `@ai-sdk/openai` as an OpenAI-compatible adapter against
 * https://integrate.api.nvidia.com/v1. `.chat()` keeps tool calling on
 * Chat Completions, not the Responses API.
 */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";

const NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1";

export function isNvidiaNimConfigured(): boolean {
  return Boolean(process.env.NVIDIA_API_KEY);
}

export function createNvidiaNimProvider() {
  return createOpenAI({
    baseURL: NVIDIA_NIM_BASE_URL,
    apiKey: process.env.NVIDIA_API_KEY,
    name: "nvidia-nim",
  });
}

/**
 * LanguageModel for Chat Completions. Throws a sanitised auth error when
 * the NVIDIA key is missing; never interpolates the key value.
 */
export function getNvidiaNimModel(modelId: string): LanguageModel {
  if (!isNvidiaNimConfigured()) {
    throw new Error(
      "NVIDIA NIM authentication failed: missing or invalid API key",
    );
  }

  return createNvidiaNimProvider().chat(modelId);
}
