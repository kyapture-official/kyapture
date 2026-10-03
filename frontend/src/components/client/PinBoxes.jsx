import { useId, useRef } from "react";

const MIN_BOXES = 4;
const MAX_BOXES = 8; // the server accepts 4-8 digit PINs

/**
 * Pixieset-style PIN entry: one box per digit. It is ONE real numeric <input>
 * (so paste, mobile numeric keypads, autofill and screen readers all behave)
 * with the digits drawn as boxes on top. Starts with four boxes and grows
 * (up to eight) only if the PIN is longer, so no valid PIN is ever locked out.
 */
export default function PinBoxes({ value, onChange, invalid = false, disabled = false, autoFocus = false, describedBy }) {
  const inputRef = useRef(null);
  const id = useId();
  const count = Math.min(MAX_BOXES, Math.max(MIN_BOXES, value.length >= MIN_BOXES ? value.length + 1 : MIN_BOXES));

  return (
    <div className="relative" onClick={() => inputRef.current?.focus()}>
      <input
        ref={inputRef}
        id={id}
        type="password"
        inputMode="numeric"
        autoComplete="off"
        maxLength={MAX_BOXES}
        value={value}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-label="Download PIN"
        aria-invalid={invalid}
        aria-describedby={describedBy}
        onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, MAX_BOXES))}
        className="absolute inset-0 z-10 h-full w-full cursor-text opacity-0"
      />
      <div className="flex justify-center gap-2" aria-hidden="true">
        {Array.from({ length: count }, (_, index) => {
          const filled = index < value.length;
          const active = index === value.length;
          return (
            <span
              key={index}
              className={`flex h-14 min-w-0 max-w-[3rem] flex-1 items-center justify-center rounded-lg border bg-white text-2xl text-ink transition-colors ${
                invalid ? "border-red-500" : active ? "border-ink ring-1 ring-ink" : "border-cream-300"
              }`}
            >
              {filled ? "•" : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
}
