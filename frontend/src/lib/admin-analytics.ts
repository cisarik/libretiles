import { z } from "zod";

import type { AdminAnalyticsModel, AdminAnalyticsResponse } from "./types";

const nullableNumber = z.number().finite().nullable();
const recommendation = z.object({
  status: z.enum(["catalog_default", "observed_leader", "available", "insufficient_evidence"]),
  provider: z.string().nullable(),
  model_id: z.string().nullable(),
  display_name: z.string().nullable(),
  prompt_id: z.number().int().nullable(),
  prompt_name: z.string().nullable(),
  reason_codes: z.array(z.string()),
  evidence: z.object({ completed_seats: z.number().int().nonnegative(), measured_attempts: z.number().int().nonnegative(), variant_slug: z.string().nullable() }),
});

const model = z.object({
  key: z.string(), provider: z.string(), model_id: z.string(), display_name: z.string(), source: z.string(), runtime_mode: z.string(),
  is_selectable: z.boolean(), is_current_flagship: z.boolean(), catalog_order: z.number().int(), games_played: z.number().int().nonnegative(),
  seat_appearances: z.number().int().nonnegative(), completed_seats: z.number().int().nonnegative(), wins: z.number().int().nonnegative(),
  losses: z.number().int().nonnegative(), draws: z.number().int().nonnegative(), win_rate_pct: nullableNumber, avg_score: nullableNumber,
  avg_spread: nullableNumber, total_moves: z.number().int().nonnegative(), known_completion_source_moves: z.number().int().nonnegative(),
  provider_candidate_pct: nullableNumber, avg_attempt_latency_ms: nullableNumber, measured_attempts: z.number().int().nonnegative(),
  avg_provider_requests_per_turn: nullableNumber, request_measured_turns: z.number().int().nonnegative(),
}).passthrough();

export const adminAnalyticsSchema = z.object({
  analytics_schema_version: z.literal(1), as_of: z.string(),
  filters: z.object({ days: z.number().int(), source: z.enum(["all", "gameplay", "playground", "diagnostic"]), variant_slug: z.string() }),
  summary: z.object({ total_games: z.number().int(), finished_games: z.number().int(), total_plies: z.number().int(), variants_played: z.number().int(), variants: z.array(z.object({ variant_slug: z.string(), total_games: z.number().int(), finished_games: z.number().int(), total_plies: z.number().int() })), abandoned_games: z.number().int(), diagnostic_runs: z.number().int() }),
  models: z.array(model),
  presets: z.array(z.object({ prompt_id: z.number().int().nullable(), name: z.string(), games_played: z.number().int(), seat_appearances: z.number().int(), completed_seats: z.number().int(), wins: z.number().int(), losses: z.number().int(), draws: z.number().int(), win_rate_pct: nullableNumber, avg_score: nullableNumber, content_version_verified: z.literal(false) })),
  recommendations: z.object({ current_flagship: recommendation, primary_flagship: recommendation, high_throughput_rival: recommendation, offline_cpu: recommendation, strategic_preset: recommendation, reliability_notes: z.array(z.string()), changes_catalog: z.literal(false) }),
  coverage: z.object({ unknown_runtime_moves: z.number().int(), unknown_completion_source_moves: z.number().int(), limitations: z.array(z.string()) }),
});

export function parseAdminAnalytics(value: unknown): AdminAnalyticsResponse {
  return adminAnalyticsSchema.parse(value) as AdminAnalyticsResponse;
}

export type AnalyticsSortKey = "catalog" | "wins" | "win_rate_pct" | "avg_score" | "avg_spread" | "provider_candidate_pct" | "avg_attempt_latency_ms" | "avg_provider_requests_per_turn";

export function sortAnalyticsModels(rows: AdminAnalyticsModel[], key: AnalyticsSortKey, direction: "ascending" | "descending") {
  const multiplier = direction === "ascending" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const leftValue = key === "catalog" ? left.catalog_order : key === "wins" ? left.wins : left[key];
    const rightValue = key === "catalog" ? right.catalog_order : key === "wins" ? right.wins : right[key];
    if (leftValue == null && rightValue == null) return left.key.localeCompare(right.key);
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    const comparison = typeof leftValue === "number" && typeof rightValue === "number" ? leftValue - rightValue : String(leftValue).localeCompare(String(rightValue));
    return comparison === 0 ? left.key.localeCompare(right.key) : comparison * multiplier;
  });
}
