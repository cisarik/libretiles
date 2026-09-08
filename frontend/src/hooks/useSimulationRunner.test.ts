import { describe, expect, it } from "vitest";

import type { SimulationRunnerPhase, SimulationSpeed } from "./useSimulationRunner";

describe("simulation runner contracts", () => {
  it("keeps the closed phase and speed vocabularies", () => {
    const phases: SimulationRunnerPhase[] = [
      "configuring",
      "starting",
      "running",
      "paused",
      "finished",
      "stopped",
      "error",
    ];
    const speeds: SimulationSpeed[] = [0.5, 1, 2];
    expect(phases).toHaveLength(7);
    expect(speeds).toEqual([0.5, 1, 2]);
  });
});
