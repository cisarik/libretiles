import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";

export const PREMIUM_PANEL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(240px circle at var(--spotlight-x, 50%) var(--spotlight-y, 50%), rgba(251,191,36,0.10), transparent 64%), linear-gradient(180deg, rgba(25,21,18,0.88), rgba(14,12,10,0.96))",
};

export const PREMIUM_HEADER_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(360px circle at var(--spotlight-x, 28%) var(--spotlight-y, 42%), rgba(255,215,128,0.16), transparent 60%), linear-gradient(145deg, rgba(17,14,11,0.90), rgba(8,8,7,0.97))",
};

export const PREMIUM_MODAL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(460px circle at var(--spotlight-x, 50%) var(--spotlight-y, 28%), rgba(255,215,128,0.16), transparent 58%), linear-gradient(180deg, rgba(24,20,16,0.95), rgba(11,9,8,0.985))",
};

export const PREMIUM_MODAL_CARD_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(280px circle at var(--spotlight-x, 50%) var(--spotlight-y, 42%), rgba(255,215,128,0.10), transparent 62%), linear-gradient(180deg, rgba(25,21,18,0.76), rgba(12,10,8,0.84))",
};

export const PREMIUM_FOOTER_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(340px circle at var(--spotlight-x, 54%) var(--spotlight-y, 52%), rgba(255,215,128,0.14), transparent 62%), linear-gradient(145deg, rgba(16,13,11,0.90), rgba(8,8,7,0.97))",
};

export const PREMIUM_GOLD_TEXT_SHADOW_CLASS =
  "transition-[filter] duration-200 [filter:drop-shadow(0_2px_0_rgba(0,0,0,0.92))_drop-shadow(0_10px_18px_rgba(0,0,0,0.56))] group-hover:[filter:none]";

/** Gold/black chrome for the fallback ping-pong tile when Premium Look is on. */
export const PREMIUM_PING_PONG_TILE_STYLE: CSSProperties = {
  backgroundImage:
    "linear-gradient(135deg, rgba(254,240,138,0.98) 0%, rgba(251,191,36,0.95) 42%, rgba(66,32,6,0.97) 100%)",
};

export interface PingPongTileMotion {
  x: number[];
  transition: {
    duration: number;
    ease: "easeInOut";
    repeat: number;
    repeatType: "reverse";
    /** Always zero: the ping-pong must never add artificial delay. */
    delay: 0;
  };
}

/**
 * Motion for the active-attempt ping-pong tile. Reduced motion yields `null`
 * so callers render a static tile instead of any movement.
 */
export function pingPongTileMotion(
  reducedMotion: boolean,
): PingPongTileMotion | null {
  if (reducedMotion) return null;
  return {
    x: [-3, 3],
    transition: {
      duration: 0.5,
      ease: "easeInOut",
      repeat: Infinity,
      repeatType: "reverse",
      delay: 0,
    },
  };
}

/**
 * The ping-pong is bound strictly to the attempt lifecycle: an attempt is
 * visually active only while the store's active index points at it and it has
 * not failed yet.
 */
export function isAttemptPingPongActive(
  status: "pending" | "active" | "failed",
  isActiveIndex: boolean,
): boolean {
  return isActiveIndex && status !== "failed";
}

export function handlePremiumSurfacePointer(event: ReactMouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  event.currentTarget.style.setProperty("--spotlight-x", `${x}px`);
  event.currentTarget.style.setProperty("--spotlight-y", `${y}px`);
}
