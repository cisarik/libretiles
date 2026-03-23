"use client";

import { useState } from "react";
import type { ChatMessage } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  disabled?: boolean;
  onSend: (body: string) => void;
}

export function ChatPanel({ messages, disabled = false, onSend }: ChatPanelProps) {
  const [draft, setDraft] = useState("");

  function submit() {
    const body = draft.trim();
    if (!body || disabled) return;
    onSend(body);
    setDraft("");
  }

  return (
    <div className="rounded-[1.55rem] border border-white/8 bg-black p-4 shadow-[0_22px_52px_rgba(0,0,0,0.28)]">
      <div className="mb-3 text-[0.74rem] uppercase tracking-[0.34em] text-stone-500">
        Game Chat
      </div>
      <div className="flex h-52 flex-col gap-2 overflow-y-auto rounded-[1.2rem] border border-white/8 bg-white/[0.03] p-3">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-stone-500">
            No messages yet.
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`max-w-[86%] rounded-2xl px-3 py-2 text-sm ${
                message.mine
                  ? "ml-auto bg-emerald-500/16 text-emerald-50"
                  : "bg-white/[0.05] text-stone-200"
              }`}
            >
              <div className="mb-1 text-[0.68rem] uppercase tracking-[0.22em] text-stone-400">
                {message.mine ? "You" : message.author_username}
              </div>
              <div>{message.body}</div>
            </div>
          ))
        )}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={disabled ? "Chat unavailable" : "Say something"}
          disabled={disabled}
          className="min-w-0 flex-1 rounded-full border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-stone-100 outline-none transition-colors placeholder:text-stone-500 focus:border-white/26 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <button
          onClick={submit}
          disabled={disabled || draft.trim().length === 0}
          className="rounded-full border border-sky-300/28 bg-sky-500/12 px-4 py-3 text-sm font-semibold text-sky-100 transition-colors hover:border-white/36 hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
        >
          Send
        </button>
      </div>
    </div>
  );
}
