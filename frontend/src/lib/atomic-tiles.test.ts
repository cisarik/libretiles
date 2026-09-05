import { describe, expect, it } from "vitest";
import {
  UnstructuredMultigraphContextError,
  buildMoveUserPrompt,
  containsMultigraphToken,
  formatRackMultiset,
  isMultigraphToken,
} from "./prompts";
import { boardCellLetter, type BoardCell } from "./types";

/**
 * ATOMIC TILE TOKENS in the AI prompt path (MEC-C1-B).
 *
 * ⭐ Measured at the baseline `cbb2865`, a board holding `SZ` at (7,7) and `DZS`
 * at (7,8) reached the prompt builder as the eighteen-character row
 * `.......SZDZS......`, the builder's fifteen-character gate dropped exactly
 * that row, the labeled board and anchors collapsed to a raw dump plus the
 * literal `(7,7)`, and the rack `SZDZS?` was split into SIX fabricated tiles
 * `S Z D Z S ?` — including a `D`, which is not a tile in that variant at all.
 *
 * Everything here is about the boundary between tiles. Legality, scoring and
 * search are the backend's and are not re-litigated.
 */

const MULTIGRAPH_ALPHABET = ["A", "Á", "CS", "DZS", "L·L", "S", "SZ", "Z"];
const MULTIGRAPH_POINTS: Record<string, number> = {
  "?": 0,
  A: 1,
  Á: 4,
  CS: 5,
  DZS: 8,
  "L·L": 8,
  S: 1,
  SZ: 5,
  Z: 3,
};
const ENGLISH_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

function emptyGrid(): BoardCell[][] {
  return Array.from({ length: 15 }, () =>
    Array.from({ length: 15 }, () => null as BoardCell),
  );
}

function gridWith(
  cells: Array<[number, number, string, string | null]>,
): BoardCell[][] {
  const grid = emptyGrid();
  for (const [row, col, token, blankAs] of cells) {
    grid[row][col] = { token, blank_as: blankAs };
  }
  return grid;
}

/** A modern context: structured cell grid plus an ordered rack of tokens. */
function structuredContext(
  grid: BoardCell[][],
  rack: string[],
  extra: Record<string, unknown> = {},
) {
  return {
    compact_state: "ai_state_json:\n{}\n",
    ai_state: { grid, ai_rack: rack, human_score: 0, ai_score: 0 },
    is_first_move: false,
    alphabet: MULTIGRAPH_ALPHABET,
    tile_points: MULTIGRAPH_POINTS,
    ...extra,
  };
}

describe("the multigraph predicate", () => {
  it("counts CODE POINTS of one tile token, not UTF-16 units", () => {
    expect(isMultigraphToken("A")).toBe(false);
    expect(isMultigraphToken("Á")).toBe(false);
    expect(isMultigraphToken("Ž")).toBe(false);
    expect(isMultigraphToken("?")).toBe(false);
    expect(isMultigraphToken("SZ")).toBe(true);
    expect(isMultigraphToken("DZS")).toBe(true);
    expect(isMultigraphToken("L·L")).toBe(true);
    expect(isMultigraphToken("CH")).toBe(true);
  });

  it("reads a TILE SET and is false for every single-code-point alphabet", () => {
    expect(containsMultigraphToken(MULTIGRAPH_ALPHABET)).toBe(true);
    expect(containsMultigraphToken(ENGLISH_ALPHABET)).toBe(false);
    // Slovak, Czech and Polish accented tiles are one code point each in NFC.
    expect(containsMultigraphToken(["A", "Á", "Ä", "Č", "Ľ", "Ž", "Ł", "Ń"])).toBe(
      false,
    );
    expect(containsMultigraphToken([])).toBe(false);
    expect(containsMultigraphToken(Object.keys(MULTIGRAPH_POINTS))).toBe(true);
  });
});

describe("a rack of complete tokens", () => {
  it("never splits an array entry, and keeps order and duplicates", () => {
    expect(formatRackMultiset(["SZ", "DZS", "?"])).toBe("SZ DZS ?");
    expect(formatRackMultiset(["SZ", "SZ", "A", "L·L"])).toBe("SZ SZ A L·L");
    expect(formatRackMultiset([])).toBe("");
  });

  it("still handles the legacy string forms unchanged", () => {
    expect(formatRackMultiset("AEIRST?")).toBe("A E I R S T ?");
    expect(formatRackMultiset("A E I R S T ?")).toBe("A E I R S T ?");
    expect(formatRackMultiset("ÁUTO?HR")).toBe("Á U T O ? H R");
    expect(formatRackMultiset("")).toBe("");
  });
});

describe("one board cell is one atomic tile", () => {
  it("realizes a blank as its assignment and never as the physical '?'", () => {
    expect(boardCellLetter({ token: "SZ", blank_as: null })).toBe("SZ");
    expect(boardCellLetter({ token: "?", blank_as: "CS" })).toBe("CS");
    expect(boardCellLetter(null)).toBe(null);
    // A malformed blank stays OCCUPIED rather than reading as an empty square.
    expect(boardCellLetter({ token: "?", blank_as: null })).toBe("?");
  });
});

describe("buildMoveUserPrompt over a structured multigraph context", () => {
  const grid = gridWith([
    [7, 7, "SZ", null],
    [7, 8, "DZS", null],
    [8, 7, "?", "CS"],
  ]);
  const context = structuredContext(grid, ["SZ", "DZS", "?"]);

  it("renders one column per TILE with fifteen columns per row", () => {
    const prompt = buildMoveUserPrompt(context);
    expect(prompt).toContain("row 07 |.|.|.|.|.|.|.|SZ|DZS|.|.|.|.|.|.|");
    expect(prompt).toContain("row 00 |.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|");
    for (const line of prompt.split("\n")) {
      if (!line.startsWith("row ")) continue;
      const columns = line.slice(line.indexOf("|") + 1, -1).split("|");
      expect(columns).toHaveLength(15);
    }
    // ⛔ The concatenation that used to eat a column must not appear.
    expect(prompt).not.toContain("SZDZS");
    expect(prompt).not.toContain(".......SZDZS......");
  });

  it("names a blank's assignment instead of hiding it inside a letter", () => {
    const prompt = buildMoveUserPrompt(context);
    expect(prompt).toContain("row 08 |.|.|.|.|.|.|.|?=CS|.|.|.|.|.|.|.|");
    expect(prompt).toContain("'?=CS' is a blank played as CS and scores zero");
  });

  it("carries the rack as three tiles, not six letters", () => {
    const prompt = buildMoveUserPrompt(context);
    expect(prompt).toContain("RACK: SZ DZS ?");
    expect(prompt).not.toContain("RACK: S Z D Z S ?");
  });

  it("computes anchors from COORDINATES around the real tiles", () => {
    const prompt = buildMoveUserPrompt(context);
    const anchors = prompt
      .split("ANCHORS (search context, not answers):\n")[1]
      .split("\n")[0];
    expect(anchors).toBe("(6,7) (6,8) (7,6) (7,9) (8,6) (8,8) (9,7)");
    // The old degraded output was the bare literal below, with no board context.
    expect(anchors).not.toBe("(7,7)");
  });

  it("keeps the token-grid format when the board holds only single tiles", () => {
    // ⭐ The TILE SET decides the format, so it cannot flip mid-game: this is the
    // same Hungarian-shaped variant with only an `A` on the board.
    const prompt = buildMoveUserPrompt(
      structuredContext(gridWith([[7, 7, "A", null]]), ["A", "S", "Z"]),
    );
    expect(prompt).toContain("row 07 |.|.|.|.|.|.|.|A|.|.|.|.|.|.|.|");
    expect(prompt).toContain("RACK: A S Z");
  });

  it("prints the empty multigraph board as a token grid with the center anchor", () => {
    const prompt = buildMoveUserPrompt(
      structuredContext(emptyGrid(), ["SZ", "A"], { is_first_move: true }),
    );
    expect(prompt).toContain("row 07 |.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|");
    expect(prompt).toContain("(7,7) — center; first move must cover this square");
    expect(prompt).toContain("THIS IS THE FIRST MOVE — must cover center (7,7).");
  });
});

describe("the compatibility rule", () => {
  it("REJECTS an unstructured context whose tile set holds a multigraph", () => {
    const legacy = {
      compact_state:
        `grid:\n${[
          ...Array.from({ length: 7 }, () => ".".repeat(15)),
          ".......SZDZS......",
          ...Array.from({ length: 7 }, () => ".".repeat(15)),
        ].join("\n")}\nblanks:[]\nai_rack:SZDZS?\nscores: H=0 AI=0\nturn:AI\n`,
      ai_state: { ai_rack: "SZDZS?", human_score: 0, ai_score: 0 },
      is_first_move: false,
      alphabet: MULTIGRAPH_ALPHABET,
      tile_points: MULTIGRAPH_POINTS,
    };
    expect(() => buildMoveUserPrompt(legacy)).toThrow(
      UnstructuredMultigraphContextError,
    );
    try {
      buildMoveUserPrompt(legacy);
      expect.unreachable("a multigraph snapshot must never render unstructured");
    } catch (error) {
      expect(error).toBeInstanceOf(UnstructuredMultigraphContextError);
      const rejection = error as UnstructuredMultigraphContextError;
      expect(rejection.code).toBe("unstructured_multigraph_context");
      expect(rejection.message).toMatch(/CS, DZS/);
      expect(rejection.message).toMatch(/never be reconstructed/i);
    }
  });

  it("rejects a half-structured context rather than guessing the other half", () => {
    const gridOnly = {
      compact_state: "ai_state_json:\n{}\n",
      ai_state: {
        grid: gridWith([[7, 7, "SZ", null]]),
        ai_rack: "SZDZS?",
        human_score: 0,
        ai_score: 0,
      },
      is_first_move: false,
      alphabet: MULTIGRAPH_ALPHABET,
    };
    expect(() => buildMoveUserPrompt(gridOnly)).toThrow(
      UnstructuredMultigraphContextError,
    );

    const rackOnly = {
      compact_state: "ai_state_json:\n{}\n",
      ai_state: { ai_rack: ["SZ", "DZS"], human_score: 0, ai_score: 0 },
      is_first_move: false,
      alphabet: MULTIGRAPH_ALPHABET,
    };
    expect(() => buildMoveUserPrompt(rackOnly)).toThrow(
      UnstructuredMultigraphContextError,
    );

    const shortGrid = {
      compact_state: "ai_state_json:\n{}\n",
      ai_state: {
        grid: emptyGrid().slice(0, 14),
        ai_rack: ["SZ"],
        human_score: 0,
        ai_score: 0,
      },
      is_first_move: false,
      alphabet: MULTIGRAPH_ALPHABET,
    };
    expect(() => buildMoveUserPrompt(shortGrid)).toThrow(
      UnstructuredMultigraphContextError,
    );
  });

  it("lets a legacy single-code-point context through the old string path", () => {
    const rows = Array.from({ length: 15 }, (_, row) =>
      row === 7 ? ".......RATE...." : ".".repeat(15),
    );
    const legacy = {
      compact_state: `grid:\n${rows.join(
        "\n",
      )}\nblanks:[]\nai_rack:AEIRST?\nscores: H=0 AI=0\nturn:AI\n`,
      ai_state: { ai_rack: "AEIRST?", human_score: 0, ai_score: 0 },
      is_first_move: false,
    };
    const prompt = buildMoveUserPrompt(legacy);
    expect(prompt).toContain("row 07 |.......RATE....|");
    expect(prompt).toContain("RACK: A E I R S T ?");
    expect(prompt).toContain("(6,7)");
  });

  it("refuses to pack a multigraph grid even with no tile snapshot at all", () => {
    // ⛔ Evidence, not suspicion: with no snapshot the board and rack are still
    // inspected, so good structured data can never be flattened into a lie.
    const prompt = buildMoveUserPrompt({
      compact_state: "ai_state_json:\n{}\n",
      ai_state: {
        grid: gridWith([[7, 7, "SZ", null]]),
        ai_rack: ["SZ", "A"],
        human_score: 0,
        ai_score: 0,
      },
      is_first_move: false,
    });
    expect(prompt).toContain("row 07 |.|.|.|.|.|.|.|SZ|.|.|.|.|.|.|.|");
    expect(prompt).toContain("RACK: SZ A");
  });
});
