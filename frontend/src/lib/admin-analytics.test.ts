import { expect, it } from "vitest";

import { parseAdminAnalytics, sortAnalyticsModels } from "./admin-analytics";
import type { AdminAnalyticsModel } from "./types";

const row = (key: string, score: number | null): AdminAnalyticsModel => ({ key, provider: "test", model_id: key, display_name: key, source: "catalog", runtime_mode: "provider", is_selectable: true, is_current_flagship: false, catalog_order: 1, games_played: 1, seat_appearances: 1, completed_seats: 1, wins: 1, losses: 0, draws: 0, win_rate_pct: 100, avg_score: score, avg_spread: -2, total_moves: 1, known_completion_source_moves: 1, provider_candidate_pct: 100, avg_attempt_latency_ms: 20, measured_attempts: 1, avg_provider_requests_per_turn: 1, request_measured_turns: 1 });

it("sorts measured analytics before null in either direction", () => {
  expect(sortAnalyticsModels([row("unknown", null), row("low", -4), row("high", 8)], "avg_score", "ascending").map((item) => item.key)).toEqual(["low", "high", "unknown"]);
  expect(sortAnalyticsModels([row("unknown", null), row("low", -4), row("high", 8)], "avg_score", "descending").map((item) => item.key)).toEqual(["high", "low", "unknown"]);
});

it("rejects an unsupported analytics schema", () => {
  expect(() => parseAdminAnalytics({ analytics_schema_version: 2 })).toThrow();
});
