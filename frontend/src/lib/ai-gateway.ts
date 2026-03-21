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

const AI_GATEWAY_API_KEY = process.env.AI_GATEWAY_API_KEY;
const AI_GATEWAY_BASE_URL =
  process.env.AI_GATEWAY_BASE_URL || "https://ai-gateway.vercel.sh/v1";
const DEFAULT_MODEL =
  process.env.NEXT_PUBLIC_DEFAULT_MODEL || "openai/gpt-5.4";

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

/**
 * Get a LanguageModel instance for the given model ID.
 * Uses .chat() to force Chat Completions API (not Responses API).
 */
export function getModel(modelId?: string): LanguageModel {
  const id = modelId || DEFAULT_MODEL;

  if (isGatewayConfigured()) {
    const provider = createGatewayProvider();
    return provider.chat(id);
  }

  return getDirectModel(id);
}

export function getDefaultModelId(): string {
  return DEFAULT_MODEL;
}
