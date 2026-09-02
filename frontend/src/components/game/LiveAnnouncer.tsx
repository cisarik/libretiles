"use client";

import { useT } from "@/lib/i18n";

export function composeAnnouncement(input: {
  toastMessage?: string | null;
  turnStatusText?: string | null;
}): string {
  const toast = input.toastMessage;
  if (typeof toast === "string" && toast.trim() !== "") {
    return toast;
  }
  const turn = input.turnStatusText;
  if (typeof turn === "string" && turn.trim() !== "") {
    return turn;
  }
  return "";
}

export function LiveAnnouncer({ message }: { message: string }) {
  const { t } = useT();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={t("a11y.status.turn")}
      className="sr-only"
    >
      {message}
    </div>
  );
}
