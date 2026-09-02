"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  adoptBrowserLocaleIfUnset,
  useGameStore,
} from "@/hooks/useGameStore";
import {
  localeSyncDecision,
  writeLocaleCookie,
  type Locale,
} from "./locales";

const LocaleContext = createContext<Locale | null>(null);

function browserLanguages(): readonly string[] {
  if (typeof navigator === "undefined") return [];
  if (navigator.languages && navigator.languages.length > 0) {
    return Array.from(navigator.languages);
  }
  return navigator.language ? [navigator.language] : [];
}

export function LocaleProvider({
  value,
  children,
}: {
  value: Locale;
  children: ReactNode;
}) {
  const router = useRouter();

  useEffect(() => {
    const apply = () => {
      const resolved = adoptBrowserLocaleIfUnset(browserLanguages());
      const decision = localeSyncDecision(value, resolved);
      if (decision.cookie) writeLocaleCookie(decision.cookie);
      if (decision.refresh) router.refresh();
    };
    if (useGameStore.persist.hasHydrated()) {
      apply();
      return;
    }
    return useGameStore.persist.onFinishHydration(apply);
  }, [value, router]);

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useServerLocale(): Locale | null {
  return useContext(LocaleContext);
}
