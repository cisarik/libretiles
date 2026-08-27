import { describe, expect, it } from "vitest";
import { probeProviderCapability } from "./provider-capability";

const liveProbeEnabled = process.env.PROVIDER_PROBE_LIVE === "1";

describe.skipIf(!liveProbeEnabled)("explicit live provider capability probe", () => {
  it(
    "passes one exact provider/model pair without fallback",
    { timeout: 70_000 },
    async () => {
      const result = await probeProviderCapability({
        provider: process.env.PROVIDER_PROBE_PROVIDER,
        model: process.env.PROVIDER_PROBE_MODEL,
      });

      // This is the sole application output. Vitest's own reporter output is
      // expected, but provider errors and environment values are never printed.
      console.log(JSON.stringify(result));
      expect(result.status).toBe("pass");
    },
  );
});
