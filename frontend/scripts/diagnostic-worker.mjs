/**
 * Long-lived plain-Node diagnostic worker (fake mode).
 *
 * One process per DiagnosticRun. stdin/stdout JSONL IPC, no token on the
 * wire: the JWT arrives via LIBRETILES_AI_PLAY_JWT in this process's
 * whitelisted environment and is passed to runDiagnosticTurn's `token` only.
 * It is never logged, never placed on argv, and never echoed into an IPC
 * line. Dies on stdin EOF.
 *
 * Drives turns through the REAL /api/ai/move POST handler (K2 import path,
 * in-repo). The fetch guard blocks every origin except BACKEND_URL, so a
 * fake-mode run cannot reach a provider even by accident.
 */

import { createInterface } from "node:readline";
import { installDiagnosticResolveHooks } from "./diagnostic-resolve-hooks.mjs";

installDiagnosticResolveHooks();

const backendUrl = (process.env.BACKEND_URL ?? "").replace(/\/$/, "");
const token = process.env.LIBRETILES_AI_PLAY_JWT ?? "";
const optionalScript = process.env.LIBRETILES_AI_PLAY_SCRIPT;

if (!backendUrl) {
  process.stdout.write(
    `${JSON.stringify({ status: "error", message: "BACKEND_URL is not set" })}\n`,
  );
  process.exit(2);
}

const { installFetchGuard, runDiagnosticTurn } = await import("@/lib/ai-play-diagnostic");
const route = await import("@/app/api/ai/move/route");

const guard = installFetchGuard(new URL(backendUrl).origin, { mode: "fake" });

function scrub(message) {
  const base = typeof message === "string" ? message : String(message);
  if (!token) return base.slice(0, 300);
  return base.split(token).join("[redacted]").slice(0, 300);
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

async function runTurn(command) {
  const observation = await runDiagnosticTurn({
    post: (request) => route.POST(request),
    backendUrl,
    gameId: command.game_id,
    token,
    provider: command.provider,
    modelId: command.model_id,
    timeoutSeconds: command.timeout_seconds,
    maxSteps: command.max_steps,
    queueMode: command.queue_mode === "catalog-fallback" ? "catalog-fallback" : "selected-only",
    script: command.script,
    aiSlot: command.ai_slot ?? 1,
    backendOrigins: guard.backend,
    foreignOrigins: guard.foreign,
    providerOrigins: guard.provider,
    executedRuntimeMode: "fake",
    driver: "fake",
    // S7: the ONLY target field crossing IPC is the selection-assertion id.
    // No target URL, no credential environment name, no secret.
    ...(typeof command.diagnostic_target_id === "string" && command.diagnostic_target_id
      ? { diagnosticTargetId: command.diagnostic_target_id }
      : {}),
  });
  return observation;
}

const rl = createInterface({ input: process.stdin, terminal: false });

for await (const line of rl) {
  if (!line.trim()) continue;
  let command;
  try {
    command = JSON.parse(line);
  } catch {
    emit({ status: "error", message: "unparseable command line" });
    continue;
  }
  if (command?.cmd === "shutdown") {
    guard.restore();
    process.exit(0);
  }
  if (command?.cmd !== "run_turn") {
    emit({ status: "error", message: "unknown command" });
    continue;
  }
  const script =
    typeof command.script === "string" && command.script
      ? command.script
      : (optionalScript ?? "generic_unchanged");
  const effective = { ...command, script };
  try {
    const observation = await runTurn(effective);
    emit({ seq: command.seq, status: "done", observation });
  } catch (error) {
    emit({ seq: command.seq, status: "error", message: scrub(error?.message ?? error) });
  }
}

guard.restore();
process.exit(0);
