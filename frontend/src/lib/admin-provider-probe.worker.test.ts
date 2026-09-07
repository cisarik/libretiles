import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const workerPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../scripts/probe-worker.mjs",
);
const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);

function runWorker(payload: unknown) {
  return new Promise<{ stdout: string; stderr: string; code: number | null }>(
    (resolve, reject) => {
      const child = spawn(process.execPath, [workerPath], {
        cwd: frontendRoot,
        env: process.env,
        stdio: ["pipe", "pipe", "pipe"],
      });
      let stdout = "";
      let stderr = "";
      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => {
        stdout += chunk;
      });
      child.stderr.on("data", (chunk: string) => {
        stderr += chunk;
      });
      child.on("error", reject);
      child.on("close", (code: number | null) =>
        resolve({ stdout, stderr, code }),
      );
      child.stdin.end(JSON.stringify(payload));
    },
  );
}

describe("admin probe worker", () => {
  it("returns a fake simulated PASS without provider env", async () => {
    const result = await runWorker({
      version: 1,
      mode: "fake",
      provider: "groq",
      model: "openai/gpt-oss-120b",
    });
    const payload = JSON.parse(result.stdout) as {
      status: string;
      outbound_count: number;
      reason_code: string;
      executed_runtime_mode: string;
    };
    expect(payload.status).toBe("pass");
    expect(payload.outbound_count).toBe(0);
    expect(payload.reason_code).toBe("simulated");
    expect(payload.executed_runtime_mode).toBe("fake");
    expect(result.stderr).not.toMatch(/GROQ_API_KEY|sk-/);
  }, 20_000);

  it("rejects diagnostic target fields before runtime construction", async () => {
    const result = await runWorker({
      version: 1,
      mode: "fake",
      provider: "groq",
      model: "openai/gpt-oss-120b",
      diagnostic_target_id: "should-not-pass",
    });
    const payload = JSON.parse(result.stdout) as { reason_code: string };
    expect(payload.reason_code).toBe("malformed_output");
  }, 20_000);
});
