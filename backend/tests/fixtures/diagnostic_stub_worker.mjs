/**
 * Stub Node diagnostic worker for Python-loop runner tests.
 *
 * Protocol-compatible with frontend/scripts/diagnostic-worker.mjs (JSONL IPC
 * over stdin/stdout, dies on stdin EOF) so the Django runner loop can be
 * exercised without importing Next.js. Also dumps its received environment
 * and every IPC command line it was handed, so tests can prove the env
 * whitelist and that no token ever crosses the IPC boundary.
 *
 * Knobs (env):
 *   STUB_DELAY_MS            sleep before each answer (default 0)
 *   STUB_DIE_AFTER           exit(0) after N answered turns (0 = never)
 *   STUB_DIE_BEFORE_TURN     exit(0) upon receiving turn N, before answering
 *   STUB_COMPLETION_SOURCE   completion_source to report ("" = generic_error)
 *   STUB_REQUESTS_PER_TURN   turn_provider_requests_used to report (default 0)
 *   STUB_ENV_DUMP            path to write this process's env JSON
 *   STUB_IPC_DUMP            path to append every received command line
 */

import { appendFileSync, writeFileSync } from "node:fs";
import { createInterface } from "node:readline";

const delayMs = Number(process.env.STUB_DELAY_MS ?? "0");
const dieAfter = Number(process.env.STUB_DIE_AFTER ?? "0");
const dieBeforeTurn = Number(process.env.STUB_DIE_BEFORE_TURN ?? "0");
const completionSource = process.env.STUB_COMPLETION_SOURCE ?? "";
const requestsPerTurn = Number(process.env.STUB_REQUESTS_PER_TURN ?? "0");
const envDump = process.env.STUB_ENV_DUMP ?? "";
const ipcDump = process.env.STUB_IPC_DUMP ?? "";

if (envDump) writeFileSync(envDump, `${JSON.stringify(process.env)}\n`, "utf8");

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

let turns = 0;
const rl = createInterface({ input: process.stdin, terminal: false });

for await (const line of rl) {
  if (!line.trim()) continue;
  if (ipcDump) appendFileSync(ipcDump, `${line}\n`, "utf8");
  let command;
  try {
    command = JSON.parse(line);
  } catch {
    emit({ status: "error", message: "unparseable command line" });
    continue;
  }
  if (command?.cmd === "shutdown") {
    process.exit(0);
  }
  if (command?.cmd !== "run_turn") {
    emit({ status: "error", message: "unknown command" });
    continue;
  }
  turns += 1;
  if (dieBeforeTurn > 0 && turns >= dieBeforeTurn) process.exit(0);
  if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
  const observation = completionSource
    ? {
        terminal_kind: "done",
        action: "place",
        completion_source: completionSource,
        probe_status: "found",
        repair_attempted: false,
        terminal_cause: "ok",
        turn_provider_requests_used: requestsPerTurn,
        attempts: [],
        foreign_origins: [],
      }
    : {
        terminal_kind: "generic_error",
        action: null,
        completion_source: null,
        probe_status: null,
        repair_attempted: null,
        terminal_cause: "AI move failed",
        turn_provider_requests_used: requestsPerTurn,
        attempts: [],
        foreign_origins: [],
      };
  emit({ seq: command.seq, status: "done", observation });
  if (dieAfter > 0 && turns >= dieAfter) process.exit(0);
}

process.exit(0);
