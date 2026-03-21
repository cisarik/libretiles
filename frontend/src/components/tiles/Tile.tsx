"use client";

import { motion } from "framer-motion";
import { TILE_POINTS } from "@/lib/constants";

interface TileProps {
  letter: string;
  isBlank?: boolean;
  isPending?: boolean;
  isSelected?: boolean;
  isDragging?: boolean;
  size?: "sm" | "md" | "lg" | "board";
  hoverable?: boolean;
  onClick?: () => void;
}

const sizeClasses = {
  sm: "w-7 h-7",
  md: "w-9 h-9",
  lg: "w-[3.35rem] h-[3.35rem]",
  board: "h-[calc(90%+3px)] w-[calc(90%+3px)]",
};

const letterClasses = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-[1.55rem]",
  board: "text-[clamp(0.95rem,1vw+0.42rem,1.2rem)]",
};

const pointsClasses = {
  sm: "bottom-0.5 right-1 text-[0.5rem]",
  md: "bottom-0.5 right-1 text-[0.55rem]",
  lg: "bottom-1 right-1 text-[0.62rem]",
  board: "bottom-1 right-1.5 text-[0.68rem]",
};

export function Tile({
  letter,
  isBlank = false,
  isPending = false,
  isSelected = false,
  isDragging = false,
  size = "md",
  hoverable = true,
  onClick,
}: TileProps) {
  const points = isBlank ? 0 : (TILE_POINTS[letter] ?? 0);
  const displayLetter = letter === "?" ? "" : letter;

  return (
    <motion.div
      onClick={onClick}
      whileHover={
        !hoverable || isDragging
          ? undefined
          : { scale: size === "board" ? 1.015 : 1.035, y: size === "board" ? -1 : -2 }
      }
      whileTap={!hoverable || isDragging ? undefined : { scale: 0.97 }}
      animate={{
        scale: isDragging ? 1.08 : 1,
        rotate: isDragging ? 2 : 0,
        zIndex: isDragging ? 50 : 1,
      }}
      transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
      className={`
        relative flex items-center justify-center rounded-[0.9rem] cursor-pointer select-none
        font-black uppercase tracking-tight will-change-transform
        ${sizeClasses[size]}
        ${isBlank ? "border-dashed border-2 border-amber-400/50" : ""}
        ${isPending
          ? "bg-gradient-to-br from-amber-50 to-amber-100 text-amber-950 ring-2 ring-amber-300 shadow-[0_14px_26px_rgba(251,191,36,0.24)]"
          : "bg-gradient-to-br from-amber-50 via-[#fff4ce] to-amber-100 text-stone-800"
        }
        ${isSelected
          ? "ring-2 ring-sky-400 -translate-y-1 shadow-[0_14px_26px_rgba(56,189,248,0.22)]"
          : ""
        }
        ${isDragging ? "shadow-[0_22px_42px_rgba(0,0,0,0.42)]" : "shadow-[0_10px_18px_rgba(120,88,36,0.22),0_2px_0_rgba(255,255,255,0.34)_inset,0_-2px_0_rgba(176,124,31,0.08)_inset]"}
      `}
      style={{
        perspective: "220px",
        transform: "perspective(220px) rotateX(2deg)",
      }}
    >
      <div
        className="pointer-events-none absolute inset-[2px] rounded-[0.78rem] opacity-90"
        style={{
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.34) 0%, rgba(255,255,255,0.12) 18%, rgba(255,255,255,0) 42%, rgba(145,99,24,0.06) 100%)",
        }}
      />
      <div className="pointer-events-none absolute inset-x-[18%] top-[8%] h-[24%] rounded-full bg-white/48 blur-[10px] opacity-70" />
      <div className="pointer-events-none absolute inset-x-[14%] bottom-[8%] h-[20%] rounded-full bg-amber-900/10 blur-[12px] opacity-70" />
      <span
        className={`relative z-[1] font-black leading-none tracking-[-0.03em] drop-shadow-[0_1px_0_rgba(255,255,255,0.3)] ${letterClasses[size]}`}
      >
        {displayLetter}
      </span>
      {points > 0 && (
        <span className={`absolute z-[1] font-semibold opacity-72 ${pointsClasses[size]}`}>
          {points}
        </span>
      )}
    </motion.div>
  );
}
