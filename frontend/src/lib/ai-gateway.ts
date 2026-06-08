/**
 * Vercel AI Gateway provider configuration.
 *
 * Architecture:
 * - On Vercel (production): uses AI Gateway endpoint (ai-gateway.vercel.sh/v1)
 *   with a single AI_GATEWAY_API_KEY. Model IDs use "provider/model" format
 *   (e.g. "openai/gpt-4o-mini", "anthropic/claude-sonnet-4.6").
 *
 * - Local dev: falls back to direct provider SDK (@ai-sdk/openai) using
 *   OPENAI_API_KEY. Model IDs can be plain ("gpt-4o-mini") or prefixed.
 *
 * IMPORTANT: We explicitly use provider.chat() to force the Chat Completions
 * API (/v1/chat/completions). The default provider() call uses the Responses
 * API (/v1/responses) which the AI Gateway doesn't support for tool calling.
 *
 * See: https://vercel.com/docs/ai-gateway
 */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import { isLocalAIModelId, stripLocalAIModelPrefix } from "@/lib/local-ai";

const AI_GATEWAY_API_KEY = process.env.AI_GATEWAY_API_KEY;
const AI_GATEWAY_BASE_URL =
  process.env.AI_GATEWAY_BASE_URL || "https://ai-gateway.vercel.sh/v1";
const DEFAULT_MODEL =
  process.env.NEXT_PUBLIC_DEFAULT_MODEL || "openai/gpt-5.4";
const LM_STUDIO_BASE_URL =
  process.env.LM_STUDIO_BASE_URL || "http://localhost:1234/v1";
const LM_STUDIO_API_KEY = process.env.LM_STUDIO_API_KEY || "lm-studio";

export type AIProviderPath = "gateway" | "direct_openai" | "lmstudio";

export function isGatewayConfigured(): boolean {
  return !!AI_GATEWAY_API_KEY;
}

export function hasDirectOpenAIConfigured(): boolean {
  return !!process.env.OPENAI_API_KEY;
}

function createGatewayProvider() {
  return createOpenAI({
    baseURL: AI_GATEWAY_BASE_URL,
    apiKey: AI_GATEWAY_API_KEY,
  });
}

function createDirectProvider() {
  return createOpenAI({
    apiKey: process.env.OPENAI_API_KEY,
  });
}

function createLMStudioProvider() {
  return createOpenAI({
    baseURL: LM_STUDIO_BASE_URL,
    apiKey: LM_STUDIO_API_KEY,
    name: "lmstudio",
  });
}

/**
 * Strip "provider/" prefix for direct SDK usage.
 * "openai/gpt-4o-mini" -> "gpt-4o-mini"
 */
function stripProviderPrefix(modelId: string): string {
  const slash = modelId.indexOf("/");
  return slash >= 0 ? modelId.slice(slash + 1) : modelId;
}

export function canUseDirectOpenAIModel(modelId?: string): boolean {
  const id = modelId || DEFAULT_MODEL;
  return hasDirectOpenAIConfigured() && (id.startsWith("openai/") || !id.includes("/"));
}

export function getDirectModel(modelId?: string): LanguageModel {
  const id = modelId || DEFAULT_MODEL;
  const provider = createDirectProvider();
  return provider.chat(stripProviderPrefix(id));
}

export function getLMStudioModel(modelId?: string): LanguageModel {
  const id = stripLocalAIModelPrefix(modelId || DEFAULT_MODEL);
  const provider = createLMStudioProvider();
  return provider.chat(id);
}

export function getProviderPath(modelId?: string): AIProviderPath {
  const id = modelId || DEFAULT_MODEL;

  if (isLocalAIModelId(id)) {
    return "lmstudio";
  }

  if (isGatewayConfigured()) {
    return "gateway";
  }

  return "direct_openai";
}

/**
 * Get a LanguageModel instance for the given model ID.
 * Uses .chat() to force Chat Completions API (not Responses API).
 */
export function getModel(modelId?: string): LanguageModel {
  const id = modelId || DEFAULT_MODEL;

  if (isLocalAIModelId(id)) {
    return getLMStudioModel(id);
  }

  if (isGatewayConfigured()) {
    const provider = createGatewayProvider();
    return provider.chat(id);
  }

  return getDirectModel(id);
}

export function getDefaultModelId(): string {
  return DEFAULT_MODEL;
}
