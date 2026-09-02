"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { foldForSearch } from "@/lib/i18n/locales";
import {
  PREMIUM_PANEL_STYLE,
  handlePremiumSurfacePointer,
} from "@/lib/premiumSurface";

export interface PremiumPickerOption {
  value: string;
  label: string;
  flagSrc?: string;
  disabled?: boolean;
}

export function filterPickerOptions<T extends { label: string }>(
  options: readonly T[],
  query: string,
): T[] {
  const needle = foldForSearch(query);
  if (needle === "") return [...options];
  return options.filter((option) =>
    foldForSearch(option.label).includes(needle),
  );
}

export type PickerNavKey = "ArrowDown" | "ArrowUp" | "Home" | "End";

export function nextPickerHighlight(
  options: readonly { disabled?: boolean }[],
  currentIndex: number,
  key: PickerNavKey,
): number {
  const enabled: number[] = [];
  for (let i = 0; i < options.length; i += 1) {
    if (!options[i]?.disabled) enabled.push(i);
  }
  if (enabled.length === 0) return -1;
  const first = enabled[0]!;
  const last = enabled[enabled.length - 1]!;
  if (key === "Home") return first;
  if (key === "End") return last;
  if (key === "ArrowDown") {
    const next = enabled.find((index) => index > currentIndex);
    return next ?? first;
  }
  const earlier = enabled.filter((index) => index < currentIndex);
  return earlier.length > 0 ? earlier[earlier.length - 1]! : last;
}

function optionId(pickerId: string, value: string): string {
  return `${pickerId}-option-${value}`;
}

function FlagImage({ src }: { src: string }) {
  return (
    // Tiny 48×32 public flags. next/image exists for automatic image
    // optimization; these files total 5 KB and do not need the optimizer.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      aria-hidden="true"
      width={48}
      height={32}
      className="h-5 w-[1.875rem] shrink-0 rounded-[2px] object-cover shadow-[0_1px_2px_rgba(0,0,0,0.45)]"
    />
  );
}

export function PremiumPicker(props: {
  id: string;
  options: readonly PremiumPickerOption[];
  value: string;
  onChange: (value: string) => void;
  searchPlaceholder: string;
  emptyText: string;
  ariaLabel: string;
}) {
  const {
    id,
    options,
    value,
    onChange,
    searchPlaceholder,
    emptyText,
    ariaLabel,
  } = props;
  const listboxId = `${id}-listbox`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(-1);
  const returnFocusRef = useRef(false);

  const selected = options.find((option) => option.value === value);
  const filtered = useMemo(
    () => filterPickerOptions(options, query),
    [options, query],
  );
  const activeOption = highlight >= 0 ? filtered[highlight] : undefined;

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open || !returnFocusRef.current) return;
    returnFocusRef.current = false;
    triggerRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function openList() {
    setQuery("");
    const selectedIndex = options.findIndex(
      (option) => option.value === value && !option.disabled,
    );
    setHighlight(
      selectedIndex >= 0
        ? selectedIndex
        : nextPickerHighlight(options, -1, "ArrowDown"),
    );
    setOpen(true);
  }

  function closeList(returnFocus = false) {
    if (returnFocus) returnFocusRef.current = true;
    setOpen(false);
    setQuery("");
  }

  function selectValue(next: string) {
    onChange(next);
    closeList(true);
  }

  function onSearchKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (
      event.key === "ArrowDown" ||
      event.key === "ArrowUp" ||
      event.key === "Home" ||
      event.key === "End"
    ) {
      event.preventDefault();
      const key: PickerNavKey = event.key;
      setHighlight((current) => nextPickerHighlight(filtered, current, key));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const option = activeOption;
      if (option && !option.disabled) selectValue(option.value);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeList(true);
    }
  }

  const chromeClass =
    "relative flex w-full min-h-[3.35rem] items-center gap-3 overflow-hidden rounded-[1.15rem] border border-white/8 px-4 py-3 text-left shadow-[0_12px_28px_rgba(0,0,0,0.2)] transition-[border-color,box-shadow] duration-300 hover:border-amber-200/40 hover:shadow-[0_14px_32px_rgba(0,0,0,0.28)]";

  return (
    <div ref={rootRef} className="relative">
      {open ? (
        <input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={true}
          aria-controls={listboxId}
          aria-label={ariaLabel}
          aria-autocomplete="list"
          aria-activedescendant={
            activeOption ? optionId(id, activeOption.value) : undefined
          }
          value={query}
          placeholder={searchPlaceholder}
          onChange={(event) => {
            const nextQuery = event.target.value;
            setQuery(nextQuery);
            setHighlight(
              nextPickerHighlight(
                filterPickerOptions(options, nextQuery),
                -1,
                "ArrowDown",
              ),
            );
          }}
          onKeyDown={onSearchKeyDown}
          onMouseMove={handlePremiumSurfacePointer}
          className={`${chromeClass} text-[1.15rem] font-black tracking-[0.04em] text-stone-100 placeholder:font-semibold placeholder:text-stone-500 focus:border-amber-300/45 focus:outline-none`}
          style={PREMIUM_PANEL_STYLE}
          autoComplete="off"
          spellCheck={false}
        />
      ) : (
        <button
          ref={triggerRef}
          type="button"
          id={id}
          role="combobox"
          aria-expanded={false}
          aria-controls={listboxId}
          aria-label={ariaLabel}
          aria-haspopup="listbox"
          onClick={openList}
          onMouseMove={handlePremiumSurfacePointer}
          className={chromeClass}
          style={PREMIUM_PANEL_STYLE}
        >
          {selected?.flagSrc ? <FlagImage src={selected.flagSrc} /> : null}
          <span className="min-w-0 flex-1 truncate font-gold-shiny text-[1.2rem] font-black leading-none tracking-[0.04em] sm:text-[1.35rem]">
            {selected?.label ?? ""}
          </span>
          <svg
            viewBox="0 0 20 20"
            aria-hidden="true"
            className="h-5 w-5 shrink-0 text-amber-200/80"
          >
            <path
              fill="currentColor"
              d="M5.3 7.3a1 1 0 0 1 1.4 0L10 10.58l3.3-3.28a1 1 0 1 1 1.4 1.42l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 0 1 0-1.42z"
            />
          </svg>
        </button>
      )}

      <ul
        role="listbox"
        id={listboxId}
        hidden={!open}
        onMouseMove={handlePremiumSurfacePointer}
        className="absolute inset-x-0 top-[calc(100%+0.4rem)] z-20 overflow-hidden rounded-[1.15rem] border border-amber-300/25 py-1.5 shadow-[0_20px_45px_rgba(0,0,0,0.45)]"
        style={PREMIUM_PANEL_STYLE}
      >
        {filtered.length === 0 ? (
          <li className="px-4 py-3 text-sm uppercase tracking-[0.12em] text-stone-400">
            {emptyText}
          </li>
        ) : (
          filtered.map((option, index) => {
            const isSelected = option.value === value;
            const isActive = index === highlight;
            const disabled = Boolean(option.disabled);
            return (
              <li
                key={option.value}
                id={optionId(id, option.value)}
                role="option"
                aria-selected={isSelected}
                aria-disabled={disabled}
                data-option-value={option.value}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => {
                  if (!disabled) setHighlight(index);
                }}
                onClick={() => {
                  if (!disabled) selectValue(option.value);
                }}
                className={`flex items-center gap-3 px-4 py-2.5 ${
                  disabled
                    ? "cursor-not-allowed opacity-45"
                    : "cursor-pointer"
                } ${
                  isActive && !disabled
                    ? "bg-amber-400/12"
                    : isSelected
                      ? "bg-amber-400/8"
                      : ""
                }`}
              >
                {option.flagSrc ? <FlagImage src={option.flagSrc} /> : null}
                <span
                  className={`min-w-0 flex-1 truncate text-[1.05rem] font-black tracking-[0.04em] ${
                    isSelected && !disabled ? "text-amber-100" : "text-stone-100"
                  }`}
                >
                  {option.label}
                </span>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
