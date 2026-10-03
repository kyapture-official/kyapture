// File Location: frontend/src/components/shared/ItemMenu.jsx
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const MENU_WIDTH = 208;
const EDGE = 8;

/**
 * The three-dot "more" menu used on collection cards and photo tiles.
 *
 * - The trigger is hidden until the card is hovered (`group-hover`) or focused
 *   on a mouse device, and ALWAYS visible on touch screens
 *   (`[@media(hover:none)]`) and while the menu is open, so it can always be
 *   reached with a finger or the keyboard.
 * - The menu itself is rendered in a portal with fixed positioning, so a card's
 *   `overflow-hidden` can never clip it, and it is clamped inside the viewport.
 * - Escape / outside click / scroll close it; Up/Down/Home/End move between items.
 *
 * items: [{ key, label, onSelect, danger?, disabled?, hint?, divider? }]
 */
export default function ItemMenu({ items, label = "More actions", className = "", triggerClassName = "" }) {
  const menuId = useId();
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, up: false });

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const height = menuRef.current?.offsetHeight || 220;
    const left = Math.min(Math.max(EDGE, rect.right - MENU_WIDTH), window.innerWidth - MENU_WIDTH - EDGE);
    const fitsBelow = rect.bottom + 6 + height <= window.innerHeight - EDGE;
    setPosition({
      left,
      top: fitsBelow ? rect.bottom + 6 : Math.max(EDGE, rect.top - 6 - height),
      up: !fitsBelow,
    });
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place, items.length]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (menuRef.current?.contains(event.target) || triggerRef.current?.contains(event.target)) return;
      close(false);
    };
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close(true);
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const entries = [...(menuRef.current?.querySelectorAll('[role="menuitem"]:not([disabled])') || [])];
      if (!entries.length) return;
      event.preventDefault();
      const index = entries.indexOf(document.activeElement);
      const next =
        event.key === "Home" ? 0
          : event.key === "End" ? entries.length - 1
            : event.key === "ArrowDown" ? (index + 1) % entries.length
              : (index - 1 + entries.length) % entries.length;
      entries[next].focus();
    };
    const onViewportChange = () => close(false);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    const frame = requestAnimationFrame(() => menuRef.current?.querySelector('[role="menuitem"]:not([disabled])')?.focus());
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [open, close]);

  const stop = (event) => event.stopPropagation();

  return (
    <div className={className} onClick={stop} onKeyDown={stop} onMouseDown={stop} draggable={false}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className={`flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-white/95 text-ink shadow-sm transition-opacity duration-150 hover:bg-white focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
          open ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100"
        } ${triggerClassName}`}
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label={label}
            style={{ position: "fixed", top: position.top, left: position.left, width: MENU_WIDTH, zIndex: 130 }}
            className="overflow-hidden rounded-xl border border-cream-200 bg-surface-light py-1.5 shadow-xl"
            onClick={stop}
            onMouseDown={stop}
          >
            {items.map((item) => (
              <div key={item.key}>
                {item.divider && <div className="my-1 border-t border-cream-200" role="separator" />}
                <button
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  onClick={() => {
                    close(false);
                    item.onSelect?.();
                  }}
                  className={`flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 ${
                    item.danger
                      ? "text-red-600 hover:bg-red-50 focus-visible:bg-red-50"
                      : "text-ink hover:bg-cream-100 focus-visible:bg-cream-100"
                  }`}
                >
                  <span className="truncate">{item.label}</span>
                  {item.hint && <span className="shrink-0 text-[10px] text-muted">{item.hint}</span>}
                </button>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
