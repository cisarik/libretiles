"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { AdminReplayPly } from "@/lib/types";
import { ReplayScoreBreakdown } from "./ReplayScoreBreakdown";
import { ReplayToolTimeline } from "./ReplayToolTimeline";
import { ReplayEngineDetails } from "./ReplayEngineDetails";
import styles from "./admin.module.css";

const TABS = ["Score & Words", "AI Telemetry & Tool Calls", "Engine & Search"] as const;

export function ReplayMoveInspector({ move, onOpen }: { move: AdminReplayPly | null; onOpen?: () => void }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const id = useId();
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const toggle = () => setOpen((value) => {
    const next = !value;
    if (next) onOpen?.();
    return next;
  });
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    let next = active;
    if (event.key === "ArrowRight") next = (active + 1) % TABS.length;
    else if (event.key === "ArrowLeft") next = (active + TABS.length - 1) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    setActive(next);
    tabs.current[next]?.focus();
  };
  return <section className={`${styles.panel} overflow-hidden`}><button type="button" className={`${styles.inspectorTrigger} ${styles.button}`} aria-expanded={open} aria-controls={`${id}-content`} onClick={toggle}><span><span className="block text-left text-xs uppercase tracking-[.16em] text-stone-400">Deep move inspector</span><span className="block text-left">{move ? `Inspect stored sequence ${move.seq}` : "Initial position"}</span></span><span aria-hidden="true">{open ? "−" : "+"}</span></button>{open ? <div id={`${id}-content`} className={styles.inspectorBody}>{move ? <><div role="tablist" aria-label="Move inspection" className={styles.inspectorTabs}>{TABS.map((label, index) => <button key={label} ref={(node) => { tabs.current[index] = node; }} id={`${id}-tab-${index}`} role="tab" aria-selected={active === index} aria-controls={`${id}-panel-${index}`} tabIndex={active === index ? 0 : -1} className={styles.inspectorTab} onClick={() => setActive(index)} onKeyDown={onTabKeyDown}>{label}</button>)}</div><div role="tabpanel" id={`${id}-panel-${active}`} aria-labelledby={`${id}-tab-${active}`} className={styles.inspectorPanel}>{active === 0 ? <ReplayScoreBreakdown move={move} /> : active === 1 ? <ReplayToolTimeline move={move} /> : <ReplayEngineDetails diagnostic={move.diagnostic_ply} />}</div></> : <div className="p-4 text-sm text-stone-400">Initial position has no move-specific inspection.</div>}</div> : null}</section>;
}
