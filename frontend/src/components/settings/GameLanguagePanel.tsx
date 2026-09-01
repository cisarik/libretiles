"use client";

import { motion } from "framer-motion";

import { useT } from "@/lib/i18n";
import type { TextKey } from "@/lib/i18n/messages.en";
import type { VariantSummary } from "@/lib/types";
import {
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";

const VARIANT_NAME_KEYS: Record<string, TextKey> = {
  english: "settings.gameVariant.english",
  slovak: "settings.gameVariant.slovak",
  czech: "settings.gameVariant.czech",
  polish: "settings.gameVariant.polish",
};

export function variantDisplayName(
  variant: VariantSummary,
  translate: (key: TextKey) => string,
): string {
  const key = VARIANT_NAME_KEYS[variant.slug];
  // Fallback to the server display_name when this slug has no catalog key.
  if (key) return translate(key);
  return variant.display_name;
}

export function GameLanguagePanel({
  variants,
  selected,
  onSelect,
}: {
  variants: readonly VariantSummary[];
  selected: string;
  onSelect: (slug: string) => void;
}) {
  const { t } = useT();

  return (
    <section
      className="relative overflow-hidden rounded-[1.6rem] border border-white/8 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/20 hover:shadow-[0_20px_45px_rgba(0,0,0,0.26)] xl:col-span-2"
      style={PREMIUM_PANEL_STYLE}
      onMouseMove={handlePremiumSurfacePointer}
      data-testid="game-language-panel"
    >
      <div className="absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="mb-4">
        <h2 className="text-xl font-black uppercase tracking-[0.12em] text-stone-50 sm:text-[1.65rem]">
          <span className="font-gold-shiny">{t("settings.gameVariant.title")}</span>
        </h2>
        <p className="mt-2 text-sm uppercase tracking-[0.14em] text-stone-500">
          {t("settings.gameVariant.description")}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {variants.map((variant) => {
          const isSelected = selected === variant.slug;
          const unavailable = variant.readiness !== "playable";
          const label = variantDisplayName(variant, t);
          return (
            <motion.button
              key={variant.slug}
              type="button"
              data-variant-slug={variant.slug}
              data-variant-readiness={variant.readiness}
              disabled={unavailable}
              whileHover={unavailable ? undefined : { y: -1.5, scale: 1.01 }}
              whileTap={unavailable ? undefined : { scale: 0.985 }}
              aria-pressed={isSelected}
              aria-disabled={unavailable}
              onClick={() => {
                if (unavailable) return;
                onSelect(variant.slug);
              }}
              className={`min-h-[96px] rounded-[1.15rem] border px-4 py-4 text-left transition-[border-color,box-shadow,background-color,transform] duration-300 ${
                unavailable
                  ? "cursor-not-allowed border-white/6 bg-stone-950/40 opacity-45"
                  : isSelected
                    ? "border-amber-300/45 bg-amber-400/10 shadow-[0_12px_30px_rgba(251,191,36,0.10)]"
                    : "border-white/8 bg-stone-950/72 hover:border-white/14 hover:shadow-[0_12px_28px_rgba(0,0,0,0.2)]"
              }`}
            >
              <div
                className={`text-[1.45rem] font-black uppercase tracking-[0.08em] ${
                  isSelected && !unavailable ? "text-amber-100" : "text-stone-100"
                }`}
              >
                {label}
              </div>
            </motion.button>
          );
        })}
      </div>
    </section>
  );
}
