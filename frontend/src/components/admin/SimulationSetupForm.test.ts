import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("ships independent player difficulty sliders, prompt preview, and judge selection", () => {
  const source = readFileSync(new URL("./SimulationSetupForm.tsx", import.meta.url), "utf8");
  expect(source.match(/type="range"/g)).toHaveLength(1);
  expect(source).toContain("Player ${slot} difficulty");
  expect(source).toContain("👁 Preview Prompt");
  expect(source).toContain("⚖️ AI Judge");
  expect(source).toContain("judge_model_id");
});
