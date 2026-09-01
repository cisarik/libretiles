import { t, tf, type Locale } from "@/lib/i18n";

/**
 * Human-readable reason for who opens the board, for the starting-draw screen.
 *
 * A blank tile arrives from the backend as "?" — see
 * backend/game/services.py `_perform_starting_draw`, which maps a blank to ""
 * before comparing, so a blank sorts before every letter and therefore always
 * wins the draw. Two blanks compare equal, `"" <= ""` is true, and slot 0 (the
 * human) starts. That last case is rare but reachable, so it is named rather
 * than folded into the single-blank branch.
 *
 * Kept out of the page component so it can be tested without a renderer.
 */
export function describeDrawReason(
  locale: Locale,
  humanTile: string,
  aiTile: string,
  humanFirst: boolean,
): string {
  const humanBlank = humanTile === "?";
  const aiBlank = aiTile === "?";

  if (humanBlank && aiBlank) return t(locale, "draw.reason.bothBlank");
  if (humanBlank) return t(locale, "draw.reason.blankYou");
  if (aiBlank) return t(locale, "draw.reason.blankAi");

  return humanFirst
    ? tf(locale, "draw.reason.closer", { winner: humanTile, loser: aiTile })
    : tf(locale, "draw.reason.closer", { winner: aiTile, loser: humanTile });
}
