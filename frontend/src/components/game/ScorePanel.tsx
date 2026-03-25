"use client";

import type { ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";
import { LuxeHoverText } from "@/components/game/LuxeHoverText";
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

function IconTooltip({
  label,
  align = "center",
}: {
  label: string;
  align?: "left" | "center" | "right";
}) {
  const alignClass =
    align === "left"
      ? "left-0 translate-x-0"
      : align === "right"
        ? "right-0 translate-x-0"
        : "left-1/2 -translate-x-1/2";

  return (
    <span className={`pointer-events-none absolute bottom-full z-[300] mb-3 translate-y-1 whitespace-nowrap rounded-full border border-amber-200/26 bg-[linear-gradient(180deg,rgba(11,11,10,0.98),rgba(7,7,6,0.99))] px-3.5 py-1.5 font-gold-shiny text-[0.96rem] font-black leading-none text-amber-100 opacity-0 shadow-[0_20px_38px_rgba(0,0,0,0.44)] transition-all duration-200 group-hover:-translate-y-0.5 group-hover:opacity-100 sm:text-[1.02rem] ${alignClass}`}>
      {label}
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
    <div className="relative z-0 flex min-w-0 -translate-y-[5px] items-start gap-2.5">
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
  deltaSide = "right",
  containerClassName,
  labelClassName,
  deltaClassName,
  scoreClassName,
}: {
  score: number;
  label: ReactNode;
  delta?: number | null;
  deltaTone?: "friendly" | "rival" | "neutral";
  deltaSide?: "left" | "right";
  containerClassName?: string;
  labelClassName?: string;
  deltaClassName?: string;
  scoreClassName?: string;
}) {
  const deltaClasses =
    deltaTone === "friendly"
      ? "border-emerald-300/24 bg-emerald-400/10 text-emerald-200"
      : deltaTone === "rival"
        ? "border-amber-300/22 bg-amber-300/10 text-amber-100"
        : "border-white/12 bg-white/6 text-stone-100";

  const deltaBadge = (
    <AnimatePresence mode="popLayout">
      {delta != null && delta > 0 ? (
        <motion.div
          key={`${score}-${delta}`}
          initial={{ opacity: 0, x: deltaSide === "left" ? 8 : -8, scale: 0.88 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: deltaSide === "left" ? -8 : 8, scale: 0.9 }}
          transition={{ type: "spring", stiffness: 360, damping: 24 }}
          className={`rounded-full border px-2.75 py-[0.22rem] text-[1rem] font-black tracking-[0.06em] shadow-[0_10px_24px_rgba(0,0,0,0.18)] sm:text-[1.08rem] ${deltaClasses} ${deltaClassName ?? ""}`}
        >
          +{delta}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );

  return (
    <div className={`relative flex min-w-0 flex-col items-center gap-[0.2rem] ${containerClassName ?? ""}`}>
      <div className={`min-w-0 text-center ${labelClassName ?? ""}`}>
        {label}
      </div>
      <div className="flex items-end justify-center gap-1.5">
        {deltaSide === "left" ? deltaBadge : null}
        <AnimatePresence mode="popLayout">
          <motion.span
            key={score}
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 10, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className={`font-gold-shiny text-[2.25rem] font-black tabular-nums sm:text-[2.65rem] ${scoreClassName ?? ""}`}
          >
            {score}
          </motion.span>
        </AnimatePresence>
        {deltaSide === "right" ? deltaBadge : null}
      </div>
    </div>
  );
}

function SettingsButton({
  onClick,
  className,
  textClassName,
  iconOnly = false,
}: {
  onClick: () => void;
  className?: string;
  textClassName?: string;
  iconOnly?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`group relative h-[2.5rem] shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full border border-amber-300/22 bg-[linear-gradient(145deg,rgba(50,36,22,0.96),rgba(15,11,8,0.98))] px-3 py-2 text-center shadow-[0_16px_34px_rgba(0,0,0,0.24),0_0_28px_rgba(251,191,36,0.08)] transition-all duration-200 active:scale-[0.97] hover:border-amber-100/52 hover:bg-[linear-gradient(145deg,rgba(97,76,48,0.98),rgba(29,22,16,0.99))] hover:shadow-[0_18px_38px_rgba(0,0,0,0.28),0_0_32px_rgba(251,191,36,0.12)] sm:h-auto sm:px-4 sm:py-2.5 ${className ?? "inline-flex"}`}
    >
      {iconOnly ? (
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
            className="shrink-0 text-amber-100/92 transition-colors duration-200 group-hover:text-white"
          >
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <IconTooltip label="Settings" />
        </>
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
      <span className="text-[0.98rem] font-semibold leading-none text-white/86 sm:text-[1.04rem]">
        Balance:
      </span>
      <span className="font-gold-money text-[1.28rem] font-black leading-none sm:text-[1.4rem]">
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
  iconOnly = false,
  tooltipLabel,
  tooltipAlign = "center",
}: {
  onClick: () => void;
  label: string;
  leading?: ReactNode;
  className?: string;
  textClassName?: string;
  tone?: "neutral" | "danger";
  disabled?: boolean;
  iconOnly?: boolean;
  tooltipLabel?: string;
  tooltipAlign?: "left" | "center" | "right";
}) {
  const toneClasses =
    tone === "danger"
      ? "border-rose-300/24 bg-[linear-gradient(145deg,rgba(86,24,41,0.64),rgba(37,13,21,0.72))] hover:border-rose-100/40 hover:bg-[linear-gradient(145deg,rgba(113,31,54,0.78),rgba(55,16,30,0.82))]"
      : "border-amber-300/16 bg-[linear-gradient(145deg,rgba(34,26,18,0.88),rgba(14,11,8,0.94))] hover:border-amber-100/32 hover:bg-[linear-gradient(145deg,rgba(72,58,40,0.94),rgba(22,17,13,0.98))]";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`group relative z-[20] inline-flex h-[2.1rem] shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-center shadow-[0_12px_28px_rgba(0,0,0,0.24),0_0_24px_rgba(251,191,36,0.05)] transition-all duration-200 active:scale-[0.97] hover:z-[220] hover:shadow-[0_16px_32px_rgba(0,0,0,0.28),0_0_28px_rgba(251,191,36,0.08)] disabled:cursor-not-allowed disabled:opacity-50 ${toneClasses} ${className ?? ""}`}
    >
      {iconOnly ? (
        <>
          {leading ? <span className="text-[1rem] leading-none">{leading}</span> : null}
          <IconTooltip label={tooltipLabel ?? label} align={tooltipAlign} />
        </>
      ) : (
        <>
          {leading ? <span className="text-[0.92rem] leading-none">{leading}</span> : null}
          <LuxeHoverText className={textClassName ?? "text-[0.94rem] font-black leading-none sm:text-[1rem]"}>
            {label}
          </LuxeHoverText>
          {tooltipLabel ? <IconTooltip label={tooltipLabel} align={tooltipAlign} /> : null}
        </>
      )}
    </button>
  );
}

interface ScorePanelProps {
  opponentLabel: string;
  showRivalPicker?: boolean;
  showPromptPicker?: boolean;
  promptLabel?: string | null;
  creditBalance?: string | null;
  frameBorderColor?: string;
  onBack: () => void;
  onOpenRivalPicker: () => void;
  onOpenPromptPicker: () => void;
  onNewGame: () => void;
  onGiveUp: () => void;
  onOpenGames: () => void;
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
  showPromptPicker = false,
  promptLabel,
  creditBalance,
  frameBorderColor,
  onBack,
  onOpenRivalPicker,
  onOpenPromptPicker,
  onNewGame,
  onGiveUp,
  onOpenGames,
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
      className={`relative isolate overflow-visible rounded-[1.55rem] border border-white/8 bg-black px-3 py-1 shadow-[0_24px_56px_rgba(0,0,0,0.28)] sm:px-3.5 sm:py-1 ${premiumLookEnabled ? "backdrop-blur-[14px]" : ""}`}
      style={panelStyle}
      onMouseMove={premiumLookEnabled ? handlePremiumSurfacePointer : undefined}
    >
      {premiumLookEnabled ? (
        <>
          <div className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-amber-200/58 to-transparent" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_left,rgba(255,214,120,0.10),transparent_34%)] opacity-85" />
        </>
      ) : null}
      <div className="absolute right-[-1px] top-[-1px] z-[25] hidden items-center gap-[1px] xl:flex">
        <HeaderMiniButton
          onClick={onGiveUp}
          label={givingUp ? "Giving up..." : "Give up"}
          tone="danger"
          disabled={disableGiveUp}
          textClassName={`text-[0.94rem] font-black leading-none sm:text-[1rem] ${premiumTitleClass}`}
          tooltipLabel="Give up current game"
          tooltipAlign="right"
        />
        <HeaderMiniButton
          onClick={onLogout}
          label={loggingOut ? "Logging out..." : "Logout"}
          tone="danger"
          disabled={loggingOut}
          textClassName={`text-[0.94rem] font-black leading-none sm:text-[1rem] ${premiumTitleClass}`}
        />
      </div>
      <div className="grid gap-1 xl:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] xl:items-start xl:gap-x-4">
        <div className="hidden min-w-0 flex-col items-start gap-1 xl:flex xl:self-start">
          <LogoMark />
          <div className="flex items-center gap-[1px] xl:absolute xl:bottom-[-1px] xl:left-[-1px] xl:z-[180]">
            <button
              onClick={onBack}
              className="group relative inline-flex h-[2.86rem] w-[3.08rem] shrink-0 items-center justify-center rounded-[1.08rem] rounded-bl-[1.45rem] border border-rose-400/24 bg-[linear-gradient(145deg,rgba(96,25,46,0.62),rgba(42,14,23,0.7))] px-0 py-0 text-center shadow-[0_16px_34px_rgba(0,0,0,0.24)] transition-all duration-200 active:scale-[0.97] hover:border-rose-100/40 hover:bg-[linear-gradient(145deg,rgba(123,33,59,0.76),rgba(53,16,29,0.82))] hover:shadow-[0_18px_38px_rgba(0,0,0,0.28),0_0_26px_rgba(244,114,182,0.10)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              <span className={`text-[1.2rem] leading-none ${premiumTitleClass}`}>↩</span>
              <IconTooltip label="Back to boards" align="left" />
            </button>
            <HeaderMiniButton
              onClick={onOpenProfile}
              label="Profile"
              leading="👤"
              iconOnly
              tooltipAlign="right"
            />
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
              deltaSide="left"
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
              deltaClassName="-translate-y-[12px] border-transparent bg-emerald-400/10 text-emerald-200"
              containerClassName="relative min-w-[4.8rem] sm:min-w-[5.1rem]"
              labelClassName="flex min-h-[1.05rem] -translate-x-[20px] items-center justify-center text-[0.78rem] font-semibold tracking-[0.18em] text-white sm:text-[0.86rem]"
              scoreClassName="translate-x-[5px]"
              label={(
                <div className="relative inline-flex items-center justify-center gap-2 leading-none">
                  {showRivalPicker ? (
                    <button
                      type="button"
                      onClick={onOpenRivalPicker}
                      className="group inline-flex max-w-[8.5rem] translate-y-[5px] overflow-hidden whitespace-nowrap text-left leading-none transition-[opacity,filter] hover:opacity-92 hover:brightness-110 sm:max-w-[10.5rem] md:max-w-[12rem] lg:max-w-[15rem]"
                      title={opponentLabel}
                    >
                      <LuxeHoverText className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[1.22rem] font-black leading-none tracking-[-0.05em] sm:text-[1.48rem]">
                        {opponentLabel}
                      </LuxeHoverText>
                    </button>
                  ) : (
                    <span className="shrink-0 uppercase text-white">{opponentLabel}</span>
                  )}
                  {showPromptPicker ? (
                    <HeaderMiniButton
                      onClick={onOpenPromptPicker}
                      label="Prompt"
                      leading="📝"
                      iconOnly
                      className="h-[2.04rem] w-[2.04rem] border-amber-300/24 bg-[linear-gradient(145deg,rgba(96,74,28,0.9),rgba(29,21,12,0.96))] px-0 py-0 shadow-[0_12px_26px_rgba(0,0,0,0.22),0_0_24px_rgba(251,191,36,0.08)] hover:border-amber-100/42 hover:bg-[linear-gradient(145deg,rgba(134,104,39,0.96),rgba(39,28,16,0.98))] hover:shadow-[0_16px_30px_rgba(0,0,0,0.28),0_0_30px_rgba(251,191,36,0.12)]"
                      tooltipLabel={promptLabel ? `Prompt: ${promptLabel}` : "Prompt presets"}
                      tooltipAlign="right"
                    />
                  ) : null}
                </div>
              )}
            />
          </div>
        </div>

        <div className="flex flex-col items-center gap-1.5 xl:col-start-3 xl:items-end xl:self-start">
          <div className="flex flex-nowrap items-center justify-center gap-[1px] xl:absolute xl:bottom-[-1px] xl:right-[-1px] sm:gap-[1px]">
            <SettingsButton
              onClick={onOpenSettings}
              className="inline-flex xl:hidden"
              iconOnly
            />
            <CreditReadout
              balance={creditBalance}
              className="hidden sm:inline-flex xl:hidden"
            />
            <SettingsButton
              onClick={onOpenSettings}
              className="hidden xl:inline-flex"
              iconOnly
            />
            <HeaderMiniButton
              onClick={onOpenGames}
              label="Games"
              leading="🗂️"
              className="hidden xl:inline-flex"
              textClassName={`text-[1rem] font-black leading-none sm:text-[1.16rem] ${premiumTitleClass}`}
            />
            <button
              onClick={onNewGame}
              disabled={startingNewGame}
              className="group inline-flex h-[2.5rem] shrink-0 items-center justify-center whitespace-nowrap rounded-[1.1rem] rounded-br-[1.45rem] border border-amber-200/40 bg-[linear-gradient(135deg,rgba(251,191,36,0.18),rgba(245,158,11,0.08))] px-3.5 py-2 text-center shadow-[0_14px_30px_rgba(251,191,36,0.12),0_0_28px_rgba(251,191,36,0.12)] transition-all duration-200 active:scale-[0.97] hover:border-white/48 hover:bg-[linear-gradient(135deg,rgba(255,248,220,0.18),rgba(251,191,36,0.18),rgba(245,158,11,0.12))] hover:shadow-[0_16px_32px_rgba(255,255,255,0.06),0_0_34px_rgba(255,255,255,0.06)] disabled:cursor-not-allowed disabled:opacity-50 sm:h-auto sm:px-4 sm:py-2.5"
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
