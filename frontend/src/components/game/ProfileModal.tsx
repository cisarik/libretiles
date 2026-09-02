"use client";

import { FormEvent, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import { t as translate, useLocale, type Locale } from "@/lib/i18n";
import {
  PREMIUM_MODAL_CARD_STYLE,
  PREMIUM_MODAL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";
import type { UserProfile } from "@/lib/types";

const MODAL_TRANSITION = {
  duration: 0.24,
  ease: [0.22, 1, 0.36, 1] as const,
};

export function formatJoinedDate(
  value: string | null | undefined,
  locale: Locale,
): string {
  if (!value) return translate(locale, "history.unknownDate");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return translate(locale, "history.unknownDate");
  }
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

type Notice =
  | { tone: "success"; text: string }
  | { tone: "error"; text: string }
  | null;

export function ProfileModal({
  profile,
  onClose,
  onLogout,
  onOpenSettings,
  onChangePassword,
  loggingOut = false,
}: {
  profile: UserProfile | null;
  onClose: () => void;
  onLogout: () => void;
  onOpenSettings: () => void;
  onChangePassword: (data: {
    currentPassword: string;
    newPassword: string;
  }) => Promise<{ ok: boolean; error?: string }>;
  loggingOut?: boolean;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);
  const locale = useLocale();

  const memberSince = useMemo(
    () => formatJoinedDate(profile?.date_joined, locale),
    [profile?.date_joined, locale],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    if (!currentPassword || !newPassword || !confirmPassword) {
      setNotice({
        tone: "error",
        text: translate(locale, "profile.error.allFields"),
      });
      return;
    }
    if (newPassword !== confirmPassword) {
      setNotice({
        tone: "error",
        text: translate(locale, "profile.error.mismatch"),
      });
      return;
    }

    setSubmitting(true);
    setNotice(null);

    try {
      const result = await onChangePassword({ currentPassword, newPassword });
      if (!result.ok) {
        setNotice({
          tone: "error",
          text: result.error ?? translate(locale, "game.password.failed"),
        });
        return;
      }

      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setNotice({
        tone: "success",
        text: translate(locale, "game.password.updated"),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={MODAL_TRANSITION}
      className="fixed inset-0 z-[85] flex items-center justify-center bg-black/52 px-3 py-3 backdrop-blur-sm sm:px-4 sm:py-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 28, scale: 0.965 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.985 }}
        transition={MODAL_TRANSITION}
        className={`relative mx-auto flex max-h-[calc(100svh-1.5rem)] w-full max-w-[860px] flex-col overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(24,20,16,0.96),rgba(11,9,8,0.98))] shadow-[0_30px_100px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:max-h-[calc(100svh-2rem)] sm:rounded-[2.2rem] ${premiumLookEnabled ? "backdrop-blur-[16px]" : ""}`}
        style={premiumLookEnabled ? PREMIUM_MODAL_STYLE : undefined}
        onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(251,191,36,0.08),transparent_34%)]" />

        <div className="relative border-b border-white/8 px-4 py-4 sm:px-5 sm:py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <span className="text-[1.8rem] leading-none sm:text-[2rem]">👤</span>
                <div>
                  <div className="font-gold-shiny text-3xl font-black tracking-tight sm:text-[2.6rem]">
                    {translate(locale, "header.profile")}
                  </div>
                  <div className="mt-1 text-sm text-stone-300">
                    {translate(locale, "profile.subtitle")}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={onOpenSettings}
                className="rounded-full border border-amber-300/26 bg-[linear-gradient(135deg,rgba(251,191,36,0.12),rgba(255,255,255,0.04))] px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18),0_0_24px_rgba(251,191,36,0.08)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-200/50 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(255,255,255,0.06))] hover:shadow-[0_14px_30px_rgba(0,0,0,0.24),0_0_30px_rgba(251,191,36,0.14)]"
              >
                <span className="font-gold-shiny text-[1rem] font-black leading-none sm:text-[1.08rem]">
                  {translate(locale, "nav.settings")}
                </span>
              </motion.button>
              <motion.button
                type="button"
                whileHover={{ y: -1.5 }}
                whileTap={{ scale: 0.985 }}
                onClick={onClose}
                className="rounded-full border border-white/10 bg-white/6 px-4 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-white/18 hover:bg-white/8"
              >
                <span className="font-gold-shiny text-[1rem] font-black leading-none sm:text-[1.08rem]">
                  {translate(locale, "game.blocker.close")}
                </span>
              </motion.button>
            </div>
          </div>
        </div>

        <div className="ornate-scrollbar relative flex-1 overflow-y-auto p-4 sm:p-5">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <section
              className="relative overflow-hidden rounded-[1.8rem] border border-amber-300/20 p-4 shadow-[0_20px_55px_rgba(0,0,0,0.30)]"
              style={premiumLookEnabled ? PREMIUM_MODAL_CARD_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/70 to-transparent" />
              <div className="relative">
                <div className="text-[0.72rem] uppercase tracking-[0.24em] text-amber-100/58">
                  {translate(locale, "auth.eyebrow")}
                </div>
                <div className="mt-4 space-y-4">
                  <div>
                    <div className="text-[0.7rem] uppercase tracking-[0.22em] text-stone-500">
                      {translate(locale, "auth.field.username")}
                    </div>
                    <div className="mt-1 font-gold-shiny text-[1.55rem] font-black leading-none">
                      {profile?.username ?? translate(locale, "history.unknownDate")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.7rem] uppercase tracking-[0.22em] text-stone-500">
                      {translate(locale, "profile.email")}
                    </div>
                    <div className="mt-1 break-all text-[1rem] text-stone-200">
                      {profile?.email || translate(locale, "profile.noEmail")}
                    </div>
                  </div>
                  <div className="rounded-[1.2rem] border border-white/8 bg-black/16 px-4 py-3">
                    <div className="text-[0.7rem] uppercase tracking-[0.22em] text-stone-500">
                      {translate(locale, "profile.memberSince")}
                    </div>
                    <div className="mt-2 text-sm font-semibold text-stone-200">
                      {memberSince}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section
              className="relative overflow-hidden rounded-[1.8rem] border border-white/8 bg-[linear-gradient(180deg,rgba(17,14,11,0.76),rgba(11,9,8,0.82))] p-4 shadow-[0_18px_45px_rgba(0,0,0,0.24)]"
              style={premiumLookEnabled ? PREMIUM_MODAL_CARD_STYLE : undefined}
              onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
            >
              <div className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
              <div className="relative">
                <div className="flex items-center gap-3">
                  <span className="text-[1.6rem] leading-none">🔐</span>
                  <div>
                    <div className="font-gold-shiny text-[1.8rem] font-black tracking-tight">
                      {translate(locale, "auth.field.password")}
                    </div>
                    <div className="mt-1 text-sm text-stone-300">
                      {translate(locale, "profile.password.subtitle")}
                    </div>
                  </div>
                </div>

                {notice ? (
                  <div
                    className={`mt-4 rounded-[1.1rem] border px-4 py-3 text-sm shadow-[0_14px_32px_rgba(0,0,0,0.16)] ${
                      notice.tone === "success"
                        ? "border-emerald-300/20 bg-emerald-400/8 text-emerald-100"
                        : "border-rose-300/20 bg-rose-400/8 text-rose-100"
                    }`}
                  >
                    {notice.text}
                  </div>
                ) : null}

                <form className="mt-4 space-y-3" onSubmit={(event) => void handleSubmit(event)}>
                  <label className="block">
                    <span className="mb-2 block text-[0.72rem] uppercase tracking-[0.22em] text-stone-400">
                      {translate(locale, "profile.field.current")}
                    </span>
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(event) => setCurrentPassword(event.target.value)}
                      className="w-full rounded-[1.1rem] border border-white/10 bg-black/26 px-4 py-3 text-stone-100 outline-none transition-colors placeholder:text-stone-500 focus:border-amber-200/34"
                      placeholder={translate(locale, "profile.ph.current")}
                      autoComplete="current-password"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-[0.72rem] uppercase tracking-[0.22em] text-stone-400">
                      {translate(locale, "profile.field.new")}
                    </span>
                    <input
                      type="password"
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      className="w-full rounded-[1.1rem] border border-white/10 bg-black/26 px-4 py-3 text-stone-100 outline-none transition-colors placeholder:text-stone-500 focus:border-amber-200/34"
                      placeholder={translate(locale, "profile.ph.new")}
                      autoComplete="new-password"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-[0.72rem] uppercase tracking-[0.22em] text-stone-400">
                      {translate(locale, "profile.field.confirm")}
                    </span>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      className="w-full rounded-[1.1rem] border border-white/10 bg-black/26 px-4 py-3 text-stone-100 outline-none transition-colors placeholder:text-stone-500 focus:border-amber-200/34"
                      placeholder={translate(locale, "profile.ph.confirm")}
                      autoComplete="new-password"
                    />
                  </label>

                  <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                    <div className="text-xs text-stone-400">
                      {translate(locale, "profile.password.footnote")}
                    </div>
                    <motion.button
                      type="submit"
                      whileHover={{ y: -1.5 }}
                      whileTap={{ scale: 0.985 }}
                      disabled={submitting}
                      className="rounded-full border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-5 py-2.5 shadow-[0_10px_24px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-amber-100/60 hover:bg-[linear-gradient(135deg,rgba(251,191,36,0.24),rgba(245,158,11,0.12))] hover:shadow-[0_12px_28px_rgba(251,191,36,0.18),0_0_34px_rgba(251,191,36,0.18)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <span className="font-gold-shiny text-[1.02rem] font-black leading-none">
                        {submitting
                          ? translate(locale, "profile.submitting")
                          : translate(locale, "profile.submit")}
                      </span>
                    </motion.button>
                  </div>
                </form>
              </div>
            </section>
          </div>
        </div>

        <div className="relative border-t border-white/8 px-4 py-3 sm:px-5">
          <div className="flex justify-end">
            <motion.button
              type="button"
              whileHover={{ y: -1.5 }}
              whileTap={{ scale: 0.985 }}
              onClick={onLogout}
              disabled={loggingOut}
              className="rounded-full border border-rose-300/24 bg-rose-500/10 px-4 py-2.5 shadow-[0_10px_24px_rgba(244,63,94,0.10)] transition-[border-color,box-shadow,background-color,transform] duration-300 hover:border-rose-200/42 hover:bg-[linear-gradient(145deg,rgba(113,24,46,0.5),rgba(55,14,27,0.48))] hover:shadow-[0_14px_28px_rgba(255,255,255,0.07),0_0_24px_rgba(255,255,255,0.04)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="font-gold-shiny text-[1rem] font-black leading-none">
                {loggingOut
                  ? translate(locale, "header.loggingOut")
                  : translate(locale, "header.logout")}
              </span>
            </motion.button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
