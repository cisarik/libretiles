import { describe, expect, it } from "vitest";
import {
  JUDGE_SYSTEM_PROMPT,
  MOVE_SYSTEM_PROMPT,
  buildMoveUserPrompt,
} from "./prompts";

const MONEY_PATTERN = /USD|\$\d|sponsor|credit|bonus|paid tier/i;
const ARBITRARY_COUNT_PATTERN = /at least \d+|\d+ (?:distinct )?(?:candidate|line|move)s?\b/i;

describe("MOVE_SYSTEM_PROMPT", () => {
  it("leads with legality-first anchor search", () => {
    expect(MOVE_SYSTEM_PROMPT).toMatch(/LEGALITY FIRST/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/ANCHOR SEARCH/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/front hooks, back hooks, and premium lanes/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/first move must cross center \(7,7\)/i);
  });

  it("demands an early backend-validated scoring floor", () => {
    expect(MOVE_SYSTEM_PROMPT).toMatch(/VALIDATED SCORING FLOOR EARLY/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/backend-validated legal scoring move/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/Never return a weaker move/i);
  });

  it("keeps diverse alternatives bounded by the step budget", () => {
    expect(MOVE_SYSTEM_PROMPT).toMatch(/WHILE THE STEP BUDGET REMAINS/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/pivot to a different anchor/i);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/no required number of candidates/i);
    expect(MOVE_SYSTEM_PROMPT).not.toMatch(ARBITRARY_COUNT_PATTERN);
  });

  it("names Collins 2019 via backend validation as the sole move authority", () => {
    expect(MOVE_SYSTEM_PROMPT).toMatch(/Collins Scrabble Words \(2019\)/);
    expect(MOVE_SYSTEM_PROMPT).toMatch(/backend is the only authority/i);
  });

  it("keeps the strict JSON output contract", () => {
    expect(MOVE_SYSTEM_PROMPT).toMatch(/OUTPUT FORMAT \(strict JSON/);
    for (const field of ["action", "placements", "exchange_letters", "primary_word"]) {
      expect(MOVE_SYSTEM_PROMPT).toContain(`"${field}"`);
    }
  });

  it("is free of sponsor and money framing", () => {
    expect(MOVE_SYSTEM_PROMPT).not.toMatch(MONEY_PATTERN);
  });
});

describe("JUDGE_SYSTEM_PROMPT", () => {
  it("makes Collins 2019 the sole judge authority", () => {
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/Collins Scrabble Words \(2019\)/);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/sole validity authority/i);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/entry in Collins Scrabble Words \(2019\)/i);
  });

  it("judges conservatively toward invalid on uncertain coverage", () => {
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/conservative/i);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/cannot confidently recall/i);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/answer invalid/i);
  });

  it("contains no natural-usage override", () => {
    expect(JUDGE_SYSTEM_PROMPT).not.toMatch(/natural|idiom|corpus|attested|usage in real/i);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/Context cannot rescue a word/i);
  });

  it("requires strict one-result-per-input JSON output", () => {
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/strict JSON/i);
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/exactly one result per requested word/i);
    expect(JUDGE_SYSTEM_PROMPT).toContain('"results"');
    expect(JUDGE_SYSTEM_PROMPT).toMatch(/\{ "results": \[\{ "word"/);
  });

  it("is free of sponsor and money framing", () => {
    expect(JUDGE_SYSTEM_PROMPT).not.toMatch(MONEY_PATTERN);
  });
});

describe("buildMoveUserPrompt", () => {
  const context = {
    compact_state: "BOARD-ROWS",
    ai_state: { ai_rack: "AEIRST?", human_score: 100, ai_score: 120 },
    is_first_move: true,
  };

  it("carries rack, board state, and the first-move constraint", () => {
    const prompt = buildMoveUserPrompt(context);
    expect(prompt).toContain("RACK: AEIRST?");
    expect(prompt).toContain("BOARD-ROWS");
    expect(prompt).toContain("must cross center (7,7)");
    expect(prompt).toContain("TILE VALUES:");
    expect(prompt).toContain("PREMIUM LEGEND:");
  });

  it("echoes the floor-first, budget-aware search discipline", () => {
    const prompt = buildMoveUserPrompt(context);
    expect(prompt).toMatch(/validated scoring floor/i);
    expect(prompt).toMatch(/shared step budget/i);
    expect(prompt).toMatch(/Collins Scrabble Words 2019/);
    expect(prompt).toMatch(/finalize only .*validated/i);
  });

  it("drops the first-move note after the opening", () => {
    const prompt = buildMoveUserPrompt({ ...context, is_first_move: false });
    expect(prompt).not.toContain("must cross center (7,7)");
  });

  it("is free of sponsor and money framing", () => {
    expect(buildMoveUserPrompt(context)).not.toMatch(MONEY_PATTERN);
  });
});
