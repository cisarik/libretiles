"use client";

import { useT } from "@/lib/i18n";
import type { TextKey } from "@/lib/i18n/messages.en";
import type { VariantSummary } from "@/lib/types";
import {
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import { PremiumPicker } from "@/components/settings/PremiumPicker";

const VARIANT_NAME_KEYS: Record<string, TextKey> = {
  english: "settings.gameVariant.english",
  slovak: "settings.gameVariant.slovak",
  czech: "settings.gameVariant.czech",
  polish: "settings.gameVariant.polish",
  afrikaans: "settings.gameVariant.afrikaans",
  italian: "settings.gameVariant.italian",
  dutch: "settings.gameVariant.dutch",
  german: "settings.gameVariant.german",
  portuguese: "settings.gameVariant.portuguese",
  danish: "settings.gameVariant.danish",
  swedish: "settings.gameVariant.swedish",
  icelandic: "settings.gameVariant.icelandic",
};

// Slug-keyed rather than locale-keyed: a game variant is not an interface locale, and
// the two sets only happen to coincide today. Kept PARTIAL with a conditional spread
// so a thirteenth variant cannot silently request a missing image.
const VARIANT_FLAG_SRC: Record<string, string> = {
  english: "/en.png",
  slovak: "/sk.png",
  czech: "/cs.png",
  polish: "/pl.png",
  german: "/de.png",
  portuguese: "/pt.png",
  icelandic: "/is.png",
  italian: "/it.png",
  dutch: "/nl.png",
  danish: "/da.png",
  swedish: "/sv.png",
  afrikaans: "/af.png",
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
  const options = variants.map((variant) => {
    const flagSrc = VARIANT_FLAG_SRC[variant.slug];
    return {
      value: variant.slug,
      label: variantDisplayName(variant, t),
      ...(flagSrc ? { flagSrc } : {}),
      disabled: variant.readiness !== "playable",
    };
  });

  return (
    <section
      className="relative overflow-visible rounded-[1.6rem] border border-white/8 p-4 shadow-[0_16px_40px_rgba(0,0,0,0.22)] transition-[border-color,box-shadow,transform] duration-300 hover:border-amber-200/20 hover:shadow-[0_20px_45px_rgba(0,0,0,0.26)] xl:col-span-2"
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
      <PremiumPicker
        id="game-variant-picker"
        options={options}
        value={selected}
        onChange={onSelect}
        searchPlaceholder={t("picker.search")}
        emptyText={t("picker.noMatch")}
        ariaLabel={t("picker.gameVariantLabel")}
      />
    </section>
  );
}
