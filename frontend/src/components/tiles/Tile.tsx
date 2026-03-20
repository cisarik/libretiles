"use client";

import { motion } from "framer-motion";
import { TILE_POINTS } from "@/lib/constants";

interface TileProps {
  letter: string;
  isBlank?: boolean;
  isPending?: boolean;
  isSelected?: boolean;
  isDragging?: boolean;
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
}

const sizeClasses = {
  sm: "w-7 h-7 text-xs",
  md: "w-9 h-9 text-sm",
  lg: "w-11 h-11 text-base",
};

export function Tile({
  letter,
  isBlank = false,
  isPending = false,
  isSelected = false,
  isDragging = false,
  size = "md",
  onClick,
}: TileProps) {
  const points = isBlank ? 0 : (TILE_POINTS[letter] ?? 0);
  const displayLetter = letter === "?" ? "" : letter;

  return (
    <motion.div
      layout
      onClick={onClick}
      whileHover={{ scale: 1.05, y: -2 }}
      whileTap={{ scale: 0.95 }}
      animate={{
        scale: isDragging ? 1.15 : 1,
        rotate: isDragging ? 3 : 0,
        zIndex: isDragging ? 50 : 1,
      }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
      className={`
        relative flex items-center justify-center rounded-lg cursor-pointer select-none
        font-bold uppercase tracking-tight
        ${sizeClasses[size]}
        ${isBlank ? "border-dashed border-2 border-amber-400/50" : ""}
        ${isPending
          ? "bg-amber-100 text-amber-900 ring-2 ring-amber-400 shadow-lg shadow-amber-400/20"
          : "bg-gradient-to-br from-amber-50 to-amber-100 text-stone-800"
        }
        ${isSelected
          ? "ring-2 ring-sky-400 -translate-y-1 shadow-lg shadow-sky-400/30"
          : ""
        }
        ${isDragging ? "shadow-2xl shadow-black/40" : "shadow-md shadow-stone-400/30"}
      `}
      style={{
        perspective: "200px",
        transform: `perspective(200px) rotateX(2deg)`,
      }}
    >
      <span className="leading-none">{displayLetter}</span>
      {points > 0 && (
        <span className="absolute bottom-0.5 right-1 text-[0.5rem] font-medium opacity-70">
          {points}
        </span>
      )}
    </motion.div>
  );
}
