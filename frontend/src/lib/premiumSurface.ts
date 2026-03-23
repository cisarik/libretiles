import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";

export const PREMIUM_PANEL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(240px circle at var(--spotlight-x, 50%) var(--spotlight-y, 50%), rgba(251,191,36,0.10), transparent 64%), linear-gradient(180deg, rgba(25,21,18,0.88), rgba(14,12,10,0.96))",
};

export const PREMIUM_CREDIT_PANEL_STYLE: CSSProperties = {
  backgroundImage:
    "radial-gradient(320px circle at var(--spotlight-x, 48%) var(--spotlight-y, 45%), rgba(255,215,128,0.20), transparent 60%), linear-gradient(145deg, rgba(39,26,12,0.94), rgba(14,11,8,0.98))",
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

export function handlePremiumSurfacePointer(event: ReactMouseEvent<HTMLElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  event.currentTarget.style.setProperty("--spotlight-x", `${x}px`);
  event.currentTarget.style.setProperty("--spotlight-y", `${y}px`);
}
