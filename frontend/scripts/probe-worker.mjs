/**
 * Single-shot Node worker for Django-admin catalog capability probes.
 *
 * Fake mode returns before runtime construction. Live mode requires
 * PROVIDER_PROBE_LIVE === "1" in this process and never copies Django's
 * environment. Diagnostic target URLs and credential env names are rejected.
 */

import { installDiagnosticResolveHooks } from "./diagnostic-resolve-hooks.mjs";

installDiagnosticResolveHooks();

const { parseAdminProbeCommand, runAdminProviderProbe } = await import(
  "@/lib/admin-provider-probe"
);

const MAX_INPUT_BYTES = 4096;
const MAX_OUTPUT_BYTES = 16384;

function emit(payload) {
  const encoded = `${JSON.stringify(payload)}\n`;
  if (Buffer.byteLength(encoded, "utf8") > MAX_OUTPUT_BYTES) {
    process.stdout.write(
      `${JSON.stringify({
        version: 1,
        executed_runtime_mode: "live",
        provider: "unknown",
        model: "unknown",
        status: "unknown",
        latency_ms: null,
        outbound_count: null,
        reason_code: "malformed_output",
      })}\n`,
    );
    return;
  }
  process.stdout.write(encoded);
}

const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
  const soFar = Buffer.concat(chunks);
  if (soFar.byteLength > MAX_INPUT_BYTES) {
    emit({
      version: 1,
      executed_runtime_mode: "live",
      provider: "unknown",
      model: "unknown",
      status: "unknown",
      latency_ms: null,
      outbound_count: null,
      reason_code: "malformed_output",
    });
    process.exit(1);
  }
}

let command;
try {
  command = parseAdminProbeCommand(Buffer.concat(chunks).toString("utf8"));
} catch {
  emit({
    version: 1,
    executed_runtime_mode: "live",
    provider: "unknown",
    model: "unknown",
    status: "unknown",
    latency_ms: null,
    outbound_count: null,
    reason_code: "malformed_output",
  });
  process.exit(1);
}

if (
  Object.hasOwn(command, "diagnostic_target_id") ||
  Object.hasOwn(command, "base_url") ||
  Object.hasOwn(command, "credential_env_name")
) {
  emit({
    version: 1,
    executed_runtime_mode: command.mode,
    provider: command.provider,
    model: command.model,
    status: "unknown",
    latency_ms: null,
    outbound_count: null,
    reason_code: "malformed_output",
  });
  process.exit(1);
}

const timer = setTimeout(() => {
  emit({
    version: 1,
    executed_runtime_mode: command?.mode === "fake" ? "fake" : "live",
    provider: command?.provider ?? "unknown",
    model: command?.model ?? "unknown",
    status: "timeout",
    latency_ms: null,
    outbound_count: null,
    reason_code: "timeout",
  });
  process.exit(1);
}, 22000);

const result = await runAdminProviderProbe(command, process.env);
clearTimeout(timer);
emit(result);
process.exit(0);
