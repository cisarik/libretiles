import { describe, expect, it } from "vitest";
import {
  installFetchGuard,
  liveOptInEnabled,
  runDiagnosticTurn,
  type FakeScript,
} from "./ai-play-diagnostic";

const isWorker = process.env.LIBRETILES_AI_PLAY_WORKER === "1";

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`missing ${name}`);
  return value;
}

describe("ai-play-diagnostic live worker", () => {
  it.skipIf(isWorker)("test_live_driver_refuses_without_sentinel", () => {
    expect(liveOptInEnabled()).toBe(false);
    expect(process.env.LIBRETILES_AI_PLAY_LIVE).not.toBe("1");
  });

  it.skipIf(!isWorker)(
    "drives one real live turn against the ephemeral backend",
    { timeout: 180_000 },
    async () => {
      if (!liveOptInEnabled()) {
        throw new Error("live driver requires LIBRETILES_AI_PLAY_LIVE=1");
      }
      const backendUrl = requiredEnv("BACKEND_URL").replace(/\/$/, "");
      process.env.BACKEND_URL = backendUrl;
      const guard = installFetchGuard(new URL(backendUrl).origin, { mode: "live" });
      try {
        const { POST } = await import("@/app/api/ai/move/route");
        const script = (process.env.LIBRETILES_AI_PLAY_SCRIPT ?? "noop_rescue") as FakeScript;
        const observation = await runDiagnosticTurn({
          post: (request) => POST(request),
          backendUrl,
          gameId: requiredEnv("LIBRETILES_AI_PLAY_GAME_ID"),
          token: requiredEnv("LIBRETILES_AI_PLAY_JWT"),
          provider: requiredEnv("LIBRETILES_AI_PLAY_PROVIDER"),
          modelId: requiredEnv("LIBRETILES_AI_PLAY_MODEL_ID"),
          timeoutSeconds: Number(process.env.LIBRETILES_AI_PLAY_TIMEOUT ?? "60"),
          maxSteps: Number(process.env.LIBRETILES_AI_PLAY_MAX_STEPS ?? "30"),
          queueMode:
            process.env.LIBRETILES_AI_PLAY_QUEUE_MODE === "catalog-fallback"
              ? "catalog-fallback"
              : "selected-only",
          script,
          backendOrigins: guard.backend,
          foreignOrigins: guard.foreign,
          providerOrigins: guard.provider,
          executedRuntimeMode: "live",
          driver: "live",
        });
        observation.backend_origins = [...new Set(guard.backend)];
        observation.foreign_origins = [...new Set(guard.foreign)];
        observation.external_provider_invocations = guard.provider.length;
        observation.executed_runtime_mode = "live";
        observation.driver = "live";
        observation.sentinel_present = liveOptInEnabled();
        if (observation.foreign_origins.length > 0) {
          throw new Error(
            `diagnostic live mode blocked origin ${observation.foreign_origins[0]}`,
          );
        }
        const output = requiredEnv("LIBRETILES_AI_PLAY_OBSERVATION");
        const { writeFileSync } = await import("node:fs");
        writeFileSync(output, `${JSON.stringify(observation)}\n`, "utf8");
      } finally {
        guard.restore();
      }
    },
  );
});
