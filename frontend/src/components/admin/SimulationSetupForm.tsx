"use client";

import { useEffect, useState } from "react";

import { PremiumPicker } from "@/components/settings/PremiumPicker";
import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import type { SimulationConfig, SimulationSlotConfig } from "@/lib/admin-simulation";
import type { AIModel, AIPrompt, VariantSummary } from "@/lib/types";
import styles from "./admin.module.css";

const ENDONYMS: Record<string, string> = {
  english: "English",
  slovak: "Slovenčina",
  czech: "Čeština",
  polish: "Polski",
  german: "Deutsch",
  portuguese: "Português",
  icelandic: "Íslenska",
  italian: "Italiano",
  dutch: "Nederlands",
  danish: "Dansk",
  swedish: "Svenska",
  afrikaans: "Afrikaans",
};

const VARIANT_FLAGS: Partial<Record<string, string>> = {
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

type DraftSlot = {
  kind: "cpu" | "llm";
  modelId: string;
  promptId: string;
};

const CPU: DraftSlot = { kind: "cpu", modelId: "engine/cpu", promptId: "" };

function randomSeed(): number {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  return values[0]! & 0x7fffffff;
}

function SlotEditor({
  slot,
  value,
  models,
  prompts,
  onChange,
}: {
  slot: number;
  value: DraftSlot;
  models: AIModel[];
  prompts: AIPrompt[];
  onChange: (value: DraftSlot) => void;
}) {
  return (
    <section className={`${styles.panel} p-5`}>
      <p className="text-xs font-black uppercase tracking-[.18em] text-amber-400">Seat {slot}</p>
      <div className={`${styles.field} mt-4`}>
        <label htmlFor={`slot-${slot}-kind`}>Category</label>
        <select id={`slot-${slot}-kind`} className={styles.select} value={value.kind} onChange={(event) => onChange(event.target.value === "cpu" ? CPU : { kind: "llm", modelId: models[0]?.model_id ?? "", promptId: prompts[0] ? String(prompts[0].id) : "" })}>
          <option value="cpu">Local Engine CPU</option>
          <option value="llm" disabled={models.length === 0}>AI Model</option>
        </select>
      </div>
      {value.kind === "cpu" ? (
        <div className="mt-4 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4">
          <strong className="text-emerald-200">CPU Master</strong>
          <p className="mt-1 text-xs text-stone-400">Local ranked and witness-safe search. Zero provider calls.</p>
        </div>
      ) : (
        <div className="mt-4 grid gap-4">
          <div className={styles.field}>
            <label htmlFor={`slot-${slot}-model`}>Model</label>
            <select id={`slot-${slot}-model`} className={styles.select} value={value.modelId} onChange={(event) => onChange({ ...value, modelId: event.target.value })}>
              {models.map((model) => <option key={`${model.provider}-${model.model_id}`} value={model.model_id}>{model.display_name} · {model.provider}</option>)}
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor={`slot-${slot}-prompt`}>Prompt Preset</label>
            <select id={`slot-${slot}-prompt`} className={styles.select} value={value.promptId} onChange={(event) => onChange({ ...value, promptId: event.target.value })}>
              <option value="">TypeScript CORE only</option>
              {prompts.map((prompt) => <option key={prompt.id} value={prompt.id}>{prompt.name}</option>)}
            </select>
          </div>
        </div>
      )}
    </section>
  );
}

export function SimulationSetupForm({ token, disabled, onStart }: { token: string; disabled: boolean; onStart: (config: SimulationConfig) => void }) {
  const aiTimeout = useGameStore((state) => state.aiTimeout);
  const aiMaxSteps = useGameStore((state) => state.aiMaxSteps);
  const [models, setModels] = useState<AIModel[]>([]);
  const [prompts, setPrompts] = useState<AIPrompt[]>([]);
  const [variants, setVariants] = useState<VariantSummary[]>([]);
  const [slot0, setSlot0] = useState<DraftSlot>(CPU);
  const [slot1, setSlot1] = useState<DraftSlot>(CPU);
  const [variant, setVariant] = useState("english");
  const [seed, setSeed] = useState("");
  const [timeout, setTimeoutValue] = useState(aiTimeout);
  const [steps, setSteps] = useState(aiMaxSteps);

  useEffect(() => {
    void api.getModels().then(setModels).catch(() => setModels([]));
    void api.getPrompts().then((rows) => {
      const named = ["Initial", "Fast Search", "Short Hooks", "Grandmaster"];
      setPrompts([...rows].sort((a, b) => named.indexOf(a.name) - named.indexOf(b.name)));
    }).catch(() => setPrompts([]));
    void api.getVariants(token).then((rows) => setVariants(rows.filter((row) => row.readiness === "playable"))).catch(() => setVariants([]));
  }, [token]);

  function llmSlot(draft: DraftSlot): SimulationSlotConfig {
    if (draft.kind === "cpu") return { kind: "cpu" };
    const model = models.find((row) => row.model_id === draft.modelId);
    if (!model) return { kind: "cpu" };
    return {
      kind: "llm",
      provider: model.provider,
      model_id: model.model_id,
      prompt_id: draft.promptId ? Number(draft.promptId) : null,
    };
  }

  function modelBy(fragment: string): AIModel | undefined {
    return models.find((model) => model.model_id.includes(fragment));
  }

  const gemma = modelBy("gemma-4-31b");
  const nemotron = models.find((model) => model.provider === "nvidia-nim" && model.model_id.includes("nemotron"));
  const initialPrompt = prompts.find((prompt) => prompt.name === "Initial") ?? prompts[0];
  const llmDraft = (model: AIModel): DraftSlot => ({ kind: "llm", modelId: model.model_id, promptId: initialPrompt ? String(initialPrompt.id) : "" });

  return (
    <form className="mt-6 grid gap-5" onSubmit={(event) => {
      event.preventDefault();
      onStart({
        slot0: llmSlot(slot0),
        slot1: llmSlot(slot1),
        variant_slug: variant,
        ...(seed === "" ? {} : { seed: Number(seed) }),
        ai_timeout: timeout,
        ai_max_steps: steps,
      });
    }}>
      <div className={styles.setupGrid}>
        <SlotEditor slot={0} value={slot0} models={models} prompts={prompts} onChange={setSlot0} />
        <SlotEditor slot={1} value={slot1} models={models} prompts={prompts} onChange={setSlot1} />
      </div>
      <section className={`${styles.panel} p-5`}>
        <div className="flex flex-wrap gap-2">
          <button className={styles.button} type="button" onClick={() => { setSlot0(CPU); setSlot1(CPU); }}>CPU Master vs CPU Master</button>
          <button className={styles.button} type="button" disabled={!gemma} onClick={() => { if (gemma) { setSlot0(llmDraft(gemma)); setSlot1(CPU); } }}>Gemma 4 31B vs CPU Master</button>
          <button className={styles.button} type="button" disabled={!gemma || !nemotron} onClick={() => { if (gemma && nemotron) { setSlot0(llmDraft(nemotron)); setSlot1(llmDraft(gemma)); } }}>Nemotron vs Gemma 4</button>
        </div>
        <div className={`${styles.setupGrid} mt-5`}>
          <div className={styles.field}>
            <label>Variant</label>
            <PremiumPicker id="simulation-variant" options={variants.map((item) => { const flagSrc = VARIANT_FLAGS[item.slug]; return { value: item.slug, label: ENDONYMS[item.slug] ?? item.display_name, ...(flagSrc ? { flagSrc } : {}) }; })} value={variant} onChange={setVariant} searchPlaceholder="Search variants" emptyText="No playable variants" ariaLabel="Simulation variant" />
          </div>
          <div className={styles.field}>
            <label htmlFor="simulation-seed">Seed</label>
            <div className="flex gap-2"><input id="simulation-seed" className={styles.input} inputMode="numeric" min={0} max={2147483647} type="number" placeholder="Server generated" value={seed} onChange={(event) => setSeed(event.target.value)} /><button className={styles.button} type="button" onClick={() => setSeed(String(randomSeed()))}>Randomize</button></div>
          </div>
          <div className={styles.field}><label htmlFor="simulation-timeout">Turn timeout</label><input id="simulation-timeout" className={styles.input} type="number" min={1} max={600} value={timeout} onChange={(event) => setTimeoutValue(Number(event.target.value))} /></div>
          <div className={styles.field}><label htmlFor="simulation-steps">Provider-call budget</label><input id="simulation-steps" className={styles.input} type="number" min={5} max={100} value={steps} onChange={(event) => setSteps(Number(event.target.value))} /></div>
        </div>
      </section>
      <button type="submit" disabled={disabled || variants.length === 0} className="rounded-xl bg-amber-300 px-6 py-4 text-lg font-black text-stone-950 transition hover:bg-amber-200 disabled:opacity-40">Start Simulation</button>
    </form>
  );
}
