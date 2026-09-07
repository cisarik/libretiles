/**
 * Sibling diagnostic runtime seam (S7).
 *
 * ``getLanguageRuntime`` / ``isValidRuntimePair`` in ai-runtimes.ts stay
 * untouched and byte-behaviour-identical for the player path. The diagnostic
 * target path constructs its OWN runtime here, gated by the egress policy
 * BEFORE any credential lookup, over the Django-admin-registered target the
 * backend authorized in ``ai-context.diagnostic_runtime``.
 *
 * No base URL, no credential environment name, and no target id may flow into
 * SSE frames; those values travel Django → this module only.
 */

import type { LanguageModel } from "ai";
import { DiagnosticEgressDeniedError, assertDiagnosticEgressAllowedBeforeCredential } from "./diagnostic-egress";
import {
  createDiagnosticTargetFetch,
  createNodeResolver,
  createValidatingResolver,
  parseTargetBaseURL,
} from "./diagnostic-target-fetch";
import {
  CREDENTIAL_ENV_NAMES,
} from "./provider-logging";
import {
  createProviderRequestTracker,
  getDiagnosticOpenAICompatibleModel,
  ProviderRuntimeError,
  requireServerCredential,
  type ProviderRequestTracker,
} from "./openai-compatible";

export const DIAGNOSTIC_TARGET_PROVIDER_PREFIX = "diagnostic-target";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MODEL_ID_PATTERN = /^[\x21-\x7e]{1,200}$/;

export type DiagnosticRuntimeSpec = {
  target_id: string;
  provider: string;
  model_id: string;
  base_url: string;
  credential_env_name: string;
};

const SPEC_KEYS = "base_url,credential_env_name,model_id,provider,target_id";

export function parseDiagnosticRuntimeSpec(value: unknown): DiagnosticRuntimeSpec | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).sort().join(",") !== SPEC_KEYS) return null;
  const targetId = record.target_id;
  const provider = record.provider;
  const modelId = record.model_id;
  const baseUrl = record.base_url;
  const credentialEnvName = record.credential_env_name;
  if (
    typeof targetId !== "string" ||
    typeof provider !== "string" ||
    typeof modelId !== "string" ||
    typeof baseUrl !== "string" ||
    typeof credentialEnvName !== "string"
  ) {
    return null;
  }
  if (!UUID_PATTERN.test(targetId)) return null;
  if (provider !== `${DIAGNOSTIC_TARGET_PROVIDER_PREFIX}/${targetId}`) return null;
  if (!MODEL_ID_PATTERN.test(modelId)) return null;
  if (!(CREDENTIAL_ENV_NAMES as readonly string[]).includes(credentialEnvName)) return null;
  try {
    parseTargetBaseURL(baseUrl);
  } catch {
    return null;
  }
  return {
    target_id: targetId,
    provider,
    model_id: modelId,
    base_url: baseUrl,
    credential_env_name: credentialEnvName,
  };
}

export type DiagnosticLanguageRuntime = {
  model: LanguageModel;
  tracker: ProviderRequestTracker;
};

export async function getDiagnosticLanguageRuntime(input: {
  runtime: DiagnosticRuntimeSpec;
  tracker?: ProviderRequestTracker;
  env?: NodeJS.ProcessEnv;
}): Promise<DiagnosticLanguageRuntime> {
  const env = input.env ?? process.env;
  // Egress gate FIRST: a denied policy must fail before any credential
  // environment lookup, DNS, or socket.
  assertDiagnosticEgressAllowedBeforeCredential(env);
  const spec = input.runtime;
  if (!(CREDENTIAL_ENV_NAMES as readonly string[]).includes(spec.credential_env_name)) {
    throw new ProviderRuntimeError("provider_auth_failed");
  }
  const policy = parseTargetBaseURL(spec.base_url);
  const credentialValue = env[spec.credential_env_name];
  const apiKey = requireServerCredential(credentialValue);
  const tracker = input.tracker ?? createProviderRequestTracker();
  const customFetch = createDiagnosticTargetFetch({
    policy,
    tracker,
    provider: spec.provider,
    resolveAddresses: createValidatingResolver(createNodeResolver()),
  });
  const model = getDiagnosticOpenAICompatibleModel({
    provider: spec.provider,
    modelId: spec.model_id,
    baseURL: policy.canonicalBaseURL,
    apiKey,
    tracker,
    customFetch,
  });
  return { model, tracker };
}

export { DiagnosticEgressDeniedError };
