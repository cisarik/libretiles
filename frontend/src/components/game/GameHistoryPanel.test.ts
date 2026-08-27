import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it } from "vitest";

import { useGameStore } from "@/hooks/useGameStore";
import type { GameHistoryResponse } from "@/lib/types";
import { GameHistoryPanel } from "./GameHistoryPanel";

beforeEach(() => {
  Object.assign(useGameStore.getInitialState(), { premiumLookEnabled: false });
});

it("renders a finished null-winner outcome as Draw", () => {
  const data: GameHistoryResponse = {
    items: [
      {
        game_id: "draw-game",
        game_mode: "vs_ai",
        status: "finished",
        outcome: "draw",
        opponent_label: "AI",
        my_score: 100,
        opponent_score: 100,
        move_count: 42,
        is_my_turn: false,
        winner_slot: null,
        game_end_reason: "SIX_CONSECUTIVE_ZERO_SCORES",
        created_at: "2026-08-27T00:00:00Z",
        started_at: "2026-08-27T00:00:00Z",
        finished_at: "2026-08-27T01:00:00Z",
        updated_at: "2026-08-27T01:00:00Z",
      },
    ],
    page: 1,
    page_size: 8,
    total: 1,
    total_pages: 1,
    has_next: false,
    has_previous: false,
    game_mode: "all",
    sort: "updated",
  };

  const markup = renderToStaticMarkup(
    createElement(GameHistoryPanel, {
      data,
      filter: "all",
      sort: "updated",
      loading: false,
      error: null,
      onFilterChange: () => undefined,
      onPrevPage: () => undefined,
      onNextPage: () => undefined,
      onRefresh: () => undefined,
      onSortChange: () => undefined,
      onOpenGame: () => undefined,
    }),
  );

  expect(markup).toContain("Draw");
  expect(markup).not.toContain("Abandoned");
});
