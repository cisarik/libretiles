"use client";

import type { ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import {
  PREMIUM_GOLD_TEXT_SHADOW_CLASS,
  PREMIUM_HEADER_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";

const LOGO_TILES = [
  { letter: "T", points: 1 },
  { letter: "I", points: 1 },
  { letter: "L", points: 1 },
  { letter: "E", points: 1 },
  { letter: "S", points: 1 },
];

function formatCreditBalance(value?: string | null) {
  if (value == null || value === "") return "$--.--";
  const numeric = Number.parseFloat(value);
  if (!Number.isFinite(numeric)) return "$--.--";
  return `$${numeric.toFixed(2)}`;
}

function LuxeHoverText({
  children,
  className,
}: {
  children: string;
  className: string;
}) {
  return (
    <span className={`relative inline-grid place-items-center text-center align-middle ${className}`}>
      <span
        className="col-start-1 row-start-1 font-gold-shiny transition-opacity duration-200 group-hover:opacity-0"
      >
        {children}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none col-start-1 row-start-1 font-white-shiny opacity-0 transition-opacity duration-200 group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

function LogoTile({
  letter,
  points,
}: {
  letter: string;
  points: number;
}) {
  return (
    <div className="relative flex h-7 w-7 items-center justify-center rounded-[0.5rem] border border-stone-300/36 bg-[linear-gradient(180deg,#f8eed0,#ecddb0)] text-[1rem] font-black text-stone-900 shadow-[0_8px_16px_rgba(0,0,0,0.18),inset_0_1px_0_rgba(255,255,255,0.72)]">
      <span className="leading-none">{letter}</span>
      <span className="absolute bottom-[0.18rem] right-[0.28rem] text-[0.4rem] font-bold text-stone-700/78">
        {points}
      </span>
    </div>
  );
}

function LogoMark() {
  return (
    <div className="flex min-w-0 translate-y-[15px] items-start gap-2.5">
      <div className="font-gold-shiny text-[1.94rem] font-black leading-[0.92] tracking-tight sm:text-[2.02rem]">
        Libre
      </div>
      <div className="flex items-start gap-1 pt-0.5">
        {LOGO_TILES.map((tile) => (
          <LogoTile key={tile.letter} letter={tile.letter} points={tile.points} />
        ))}
      </div>
    </div>
  );
}

function AnimatedScore({
  score,
  label,
  delta,
  deltaTone = "neutral",
  containerClassName,
  labelClassName,
}: {
  score: number;
  label: ReactNode;
  delta?: number | null;
  deltaTone?: "friendly" | "rival" | "neutral";
  containerClassName?: string;
  labelClassName?: string;
}) {
  const deltaClasses =
    deltaTone === "friendly"
      ? "border-emerald-300/24 bg-emerald-400/10 text-emerald-100"
      : deltaTone === "rival"
        ? "border-amber-300/22 bg-amber-300/10 text-amber-100"
        : "border-white/12 bg-white/6 text-stone-100";

  return (
    <div className={`relative flex min-w-0 flex-col items-center gap-[0.2rem] ${containerClassName ?? ""}`}>
      <div className={`min-w-0 text-center ${labelClassName ?? ""}`}>
        {label}
      </div>
      <div className="flex items-end justify-center gap-1.5">
        <AnimatePresence mode="popLayout">
          <motion.span
            key={score}
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 10, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="font-gold-shiny text-[2.25rem] font-black tabular-nums sm:text-[2.65rem]"
          >
            {score}
          </motion.span>
        </AnimatePresence>
        <AnimatePresence mode="popLayout">
          {delta != null && delta > 0 ? (
            <motion.div
              key={`${score}-${delta}`}
              initial={{ opacity: 0, x: -8, scale: 0.88 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 8, scale: 0.9 }}
              transition={{ type: "spring", stiffness: 360, damping: 24 }}
              className={`mb-[1.27rem] rounded-full border px-2.5 py-[0.18rem] text-[0.86rem] font-black uppercase tracking-[0.14em] shadow-[0_10px_24px_rgba(0,0,0,0.18)] sm:mb-[1.41rem] sm:text-[0.94rem] ${deltaClasses}`}
            >
              +{delta}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}

function StatusNotice({
  text,
  tone = "neutral",
}: {
  text?: string | null;
  tone?: "active" | "waiting" | "neutral";
}) {
  const palette =
    tone === "active"
      ? "text-emerald-100"
      : tone === "waiting"
        ? "text-sky-100"
        : "text-stone-300";

  if (!text) return null;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={text}
        initial={{ opacity: 0, y: 8, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -8, scale: 0.96 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className={`inline-flex items-center gap-2 text-[1.02rem] font-semibold leading-none tracking-tight drop-shadow-[0_8px_18px_rgba(0,0,0,0.22)] sm:text-[1.12rem] ${palette}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
        <span>{text}</span>
      </motion.div>
    </AnimatePresence>
  );
}

function SettingsButton({
  onClick,
  className,
  textClassName,
  compactLabel = false,
}: {
  onClick: () => void;
  className?: string;
  textClassName?: string;
  compactLabel?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`group h-[2.5rem] shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-amber-300/18 bg-[linear-gradient(145deg,rgba(31,23,16,0.86),rgba(13,10,8,0.92))] px-3 py-2 text-center shadow-[0_14px_30px_rgba(0,0,0,0.18)] transition-all duration-200 active:scale-[0.97] hover:border-white/42 hover:bg-[linear-gradient(145deg,rgba(78,64,46,0.96),rgba(26,21,16,0.98))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.05)] sm:h-auto sm:px-4 sm:py-2.5 ${className ?? "inline-flex"}`}
      title="Settings"
    >
      {compactLabel ? (
        <span className="text-[1rem] leading-none" aria-hidden="true">⚙️</span>
      ) : (
        <>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 text-amber-100/90 transition-colors duration-200 group-hover:text-white"
          >
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <LuxeHoverText className={textClassName ?? "text-[1.12rem] font-black leading-none sm:text-[1.32rem]"}>
            Settings
          </LuxeHoverText>
        </>
      )}
    </button>
  );
}

function CreditReadout({ balance, className }: { balance?: string | null; className?: string }) {
  return (
    <div className={`inline-flex shrink-0 items-baseline justify-center gap-2 ${className ?? ""}`}>
      <span className="text-[0.94rem] font-semibold leading-none text-white/86">
        Balance:
      </span>
      <span className="font-gold-money text-[1.24rem] font-black leading-none sm:text-[1.32rem]">
        {formatCreditBalance(balance)}
      </span>
    </div>
  );
}

function HeaderMiniButton({
  onClick,
  label,
  leading,
  className,
  textClassName,
  tone = "neutral",
  disabled = false,
}: {
  onClick: () => void;
  label: string;
  leading?: ReactNode;
  className?: string;
  textClassName?: string;
  tone?: "neutral" | "danger";
  disabled?: boolean;
}) {
  const toneClasses =
    tone === "danger"
      ? "border-rose-300/20 bg-rose-500/8 hover:border-rose-200/40 hover:bg-[linear-gradient(145deg,rgba(113,24,46,0.48),rgba(55,14,27,0.42))]"
      : "border-white/10 bg-white/[0.04] hover:border-white/18 hover:bg-white/[0.07]";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`group inline-flex h-[2.1rem] shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-center shadow-[0_10px_24px_rgba(0,0,0,0.18)] transition-all duration-200 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 ${toneClasses} ${className ?? ""}`}
    >
      {leading ? <span className="text-[0.92rem] leading-none">{leading}</span> : null}
      <LuxeHoverText className={textClassName ?? "text-[0.94rem] font-black leading-none sm:text-[1rem]"}>
        {label}
      </LuxeHoverText>
    </button>
  );
}

interface ScorePanelProps {
  opponentLabel: string;
  showRivalPicker?: boolean;
  creditBalance?: string | null;
  frameBorderColor?: string;
  statusText?: string | null;
  statusTone?: "active" | "waiting" | "neutral";
  onOpenRivalPicker: () => void;
  onNewGame: () => void;
  onGiveUp: () => void;
  onOpenSettings: () => void;
  onOpenProfile: () => void;
  onLogout: () => void;
  startingNewGame?: boolean;
  givingUp?: boolean;
  disableGiveUp?: boolean;
  loggingOut?: boolean;
}

export function ScorePanel({
  opponentLabel,
  showRivalPicker = false,
  creditBalance,
  frameBorderColor,
  statusText,
  statusTone = "neutral",
  onOpenRivalPicker,
  onNewGame,
  onGiveUp,
  onOpenSettings,
  onOpenProfile,
  onLogout,
  startingNewGame = false,
  givingUp = false,
  disableGiveUp = false,
  loggingOut = false,
}: ScorePanelProps) {
  const gameState = useGameStore((s) => s.gameState);
  const premiumLookEnabled = useGameStore((s) => s.premiumLookEnabled);

  const slots = gameState?.slots ?? [];
  const mySlot = slots.find((s) => s.slot === gameState?.my_slot);
  const opponentSlot = slots.find((s) => s.slot !== gameState?.my_slot);
  const lastMovePoints =
    gameState?.last_move_points != null && gameState.last_move_points > 0
      ? gameState.last_move_points
      : null;
  const myLastGain =
    lastMovePoints != null && gameState?.last_move_player_slot === mySlot?.slot
      ? lastMovePoints
      : null;
  const opponentLastGain =
    lastMovePoints != null && gameState?.last_move_player_slot === opponentSlot?.slot
      ? lastMovePoints
      : null;
  const premiumTitleClass = premiumLookEnabled ? PREMIUM_GOLD_TEXT_SHADOW_CLASS : "";
  const panelStyle = premiumLookEnabled
    ? {
        ...(frameBorderColor ? { borderColor: frameBorderColor } : {}),
        ...PREMIUM_HEADER_STYLE,
      }
    : frameBorderColor
      ? { borderColor: frameBorderColor }
      : undefined;

  return (
    <div
      className={`relative rounded-[1.55rem] border border-white/8 bg-black px-4 py-1.5 shadow-[0_24px_56px_rgba(0,0,0,0.28)] sm:px-4.5 sm:py-1.5 ${premiumLookEnabled ? "overflow-hidden backdrop-blur-[14px]" : ""}`}
      style={panelStyle}
      onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
    >
      {premiumLookEnabled ? (
        <>
          <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/58 to-transparent" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_left,rgba(255,214,120,0.10),transparent_34%)] opacity-85" />
        </>
      ) : null}
      <div className="grid gap-1 xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] xl:items-start xl:gap-x-4">
        <div className="hidden min-w-0 flex-col items-start gap-1 xl:flex xl:self-start">
          <LogoMark />
          <div className="flex items-center gap-4 xl:-translate-x-[5px] xl:translate-y-[35px]">
            <button
              onClick={onGiveUp}
              disabled={disableGiveUp}
              className="group inline-flex h-[2.5rem] shrink-0 items-center justify-center whitespace-nowrap rounded-full border border-rose-400/22 bg-rose-500/10 px-3.5 py-2 text-center shadow-[0_14px_30px_rgba(0,0,0,0.18)] transition-all duration-200 active:scale-[0.97] hover:border-white/42 hover:bg-[linear-gradient(145deg,rgba(113,24,46,0.5),rgba(55,14,27,0.48))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_24px_rgba(255,255,255,0.04)] disabled:cursor-not-allowed disabled:opacity-45 sm:h-auto sm:px-4 sm:py-2.5 xl:-translate-x-[15px] xl:-translate-y-[1px]"
            >
              <LuxeHoverText className={`text-[1.12rem] font-black leading-none sm:text-[1.32rem] ${premiumTitleClass}`}>
                {givingUp ? "↩ Giving up..." : "↩ Give up"}
              </LuxeHoverText>
            </button>
            <CreditReadout balance={creditBalance} />
          </div>
        </div>

        <div className="flex flex-col items-center gap-0 self-center xl:col-start-2 xl:justify-self-center xl:self-start">
          <div className="grid grid-cols-[minmax(4.8rem,max-content)_auto_minmax(4.8rem,max-content)] items-end justify-center gap-3 sm:grid-cols-[minmax(5.1rem,max-content)_auto_minmax(5.1rem,max-content)] sm:gap-4">
            <AnimatedScore
              score={mySlot?.score ?? 0}
              label={mySlot?.username ?? "You"}
              delta={myLastGain}
              deltaTone="friendly"
              containerClassName="min-w-[4.8rem] sm:min-w-[5.1rem]"
              labelClassName="flex min-h-[1.05rem] translate-y-[3px] items-center justify-center text-[0.82rem] font-semibold uppercase tracking-[0.24em] text-white sm:text-[0.9rem]"
            />

            <div className="translate-x-[5px] translate-y-[5px] pb-[1.02rem] text-center text-[1.26rem] font-semibold uppercase tracking-[0.14em] text-white sm:pb-[1.14rem] sm:text-[1.36rem]">
              vs
            </div>

            <AnimatedScore
              score={opponentSlot?.score ?? 0}
              delta={opponentLastGain}
              deltaTone="rival"
              containerClassName="relative min-w-[4.8rem] sm:min-w-[5.1rem]"
              labelClassName="flex min-h-[1.05rem] items-center justify-center text-[0.78rem] font-semibold tracking-[0.18em] text-white sm:text-[0.86rem]"
              label={(
                <div className="relative inline-flex items-center justify-center gap-1 leading-none">
                  {showRivalPicker ? (
                    <>
                      <span className="shrink-0 text-[0.82rem] leading-none" aria-hidden="true">🧠</span>
                      <span className="shrink-0 uppercase text-white">AI:</span>
                      <button
                        type="button"
                        onClick={onOpenRivalPicker}
                        className="group absolute left-full top-1/2 ml-1 inline-flex max-w-[8.5rem] -translate-y-1/2 overflow-hidden whitespace-nowrap text-left leading-none transition-[opacity,filter] hover:opacity-92 hover:brightness-110 sm:max-w-[10.5rem] md:max-w-[12rem] lg:max-w-[15rem]"
                        title={opponentLabel}
                      >
                        <LuxeHoverText className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[0.94rem] font-black leading-none tracking-[-0.05em] sm:text-[1.08rem]">
                          {opponentLabel}
                        </LuxeHoverText>
                      </button>
                    </>
                  ) : (
                    <span className="shrink-0 uppercase text-white">{opponentLabel}</span>
                  )}
                </div>
              )}
            />
          </div>
          <div className="mt-[-0.06rem] grid grid-cols-[minmax(4.8rem,max-content)_auto_minmax(4.8rem,max-content)] justify-center gap-3 sm:grid-cols-[minmax(5.1rem,max-content)_auto_minmax(5.1rem,max-content)] sm:gap-4">
            <div className="flex justify-center xl:-translate-x-[20px] xl:-translate-y-[1px]">
              <StatusNotice text={statusText} tone={statusTone} />
            </div>
            <div />
            <div />
          </div>
        </div>

        <div className="flex flex-col items-center gap-1.5 xl:col-start-3 xl:items-end xl:self-start xl:translate-y-[35px]">
          <div className="hidden items-center justify-end gap-1.5 xl:flex xl:-translate-y-[15px]">
            <HeaderMiniButton
              onClick={onOpenProfile}
              label="Profile"
              leading="👤"
              textClassName={`text-[0.94rem] font-black leading-none sm:text-[1rem] ${premiumTitleClass}`}
            />
            <HeaderMiniButton
              onClick={onLogout}
              label={loggingOut ? "Logging out..." : "Logout"}
              tone="danger"
              disabled={loggingOut}
              className="xl:translate-x-[10px]"
              textClassName={`text-[0.94rem] font-black leading-none sm:text-[1rem] ${premiumTitleClass}`}
            />
          </div>
          <div className="flex flex-nowrap items-center justify-center gap-1.5 xl:-translate-y-[7px] sm:gap-2">
            <SettingsButton
              onClick={onOpenSettings}
              className="inline-flex xl:hidden"
              compactLabel
            />
            <CreditReadout
              balance={creditBalance}
              className="hidden sm:inline-flex xl:hidden"
            />
            <SettingsButton
              onClick={onOpenSettings}
              className="hidden xl:inline-flex"
              textClassName={`text-[1.12rem] font-black leading-none sm:text-[1.32rem] ${premiumTitleClass}`}
            />
            <button
              onClick={onNewGame}
              disabled={startingNewGame}
              className="group inline-flex h-[2.5rem] shrink-0 items-center justify-center whitespace-nowrap rounded-full border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-3.5 py-2 text-center shadow-[0_14px_30px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-all duration-200 active:scale-[0.97] hover:border-white/48 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.18),rgba(251,191,36,0.18),rgba(245,158,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_34px_rgba(255,255,255,0.06)] disabled:cursor-not-allowed disabled:opacity-50 sm:h-auto sm:px-4 sm:py-2.5 xl:translate-x-[15px]"
            >
              <LuxeHoverText className={`text-[1.12rem] font-black leading-none sm:text-[1.32rem] ${premiumTitleClass}`}>
                {startingNewGame ? "Starting..." : "New game"}
              </LuxeHoverText>
            </button>
          </div>
        </div>
      </div>

    </div>
  );
}
