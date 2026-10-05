// File Location: frontend/src/components/shared/ItemMenu.jsx
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const MENU_WIDTH = 208;
const EDGE = 8;
const FLYOUT_MIN_VIEWPORT = 640;
const ITEM_CLASS =
  "flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-40";

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
 * items: [{ key, label, onSelect, danger?, disabled?, hint?, divider?, children? }]
 *
 * An item with `children` ([{ key, label, onSelect | href }]) is a submenu parent
 * (e.g. Share). On a wide screen its children open in a flyout beside the menu on
 * hover / click / ArrowRight; on a narrow screen (phones) they expand inline under
 * the parent on tap, so nothing can overflow the viewport. ArrowLeft closes the
 * submenu and returns focus to the parent; Escape closes the whole menu and returns
 * focus to the trigger. A child with `href` renders as a link (e.g. mailto:).
 */
export default function ItemMenu({ items, label = "More actions", className = "", triggerClassName = "" }) {
  const menuId = useId();
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, up: false, flyout: null });
  const [subOpen, setSubOpen] = useState(null); // key of the item whose submenu is open
  const [flyUp, setFlyUp] = useState(false); // flyout anchored to the row's bottom edge (near the viewport bottom)

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    setSubOpen(null);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const height = menuRef.current?.offsetHeight || 220;
    const left = Math.min(Math.max(EDGE, rect.right - MENU_WIDTH), window.innerWidth - MENU_WIDTH - EDGE);
    const fitsBelow = rect.bottom + 6 + height <= window.innerHeight - EDGE;
    // A flyout needs room for a second column on one side; otherwise submenus expand inline.
    const wide = window.innerWidth >= FLYOUT_MIN_VIEWPORT;
    const flyout = !wide ? null
      : left + MENU_WIDTH * 2 + EDGE <= window.innerWidth ? "right"
        : left - MENU_WIDTH >= EDGE ? "left" : null;
    setPosition({
      left,
      top: fitsBelow ? rect.bottom + 6 : Math.max(EDGE, rect.top - 6 - height),
      up: !fitsBelow,
      flyout,
    });
  }, []);

  // Opens a submenu; `focusFirst` moves focus to its first entry (keyboard).
  const openSub = useCallback((key, focusFirst = false) => {
    const row = menuRef.current?.querySelector(`[data-parent="${key}"]`);
    if (row) setFlyUp(row.getBoundingClientRect().top + 200 > window.innerHeight - EDGE);
    setSubOpen(key);
    if (focusFirst) {
      requestAnimationFrame(() =>
        menuRef.current?.querySelector(`[data-submenu="${key}"] [role="menuitem"]`)?.focus(),
      );
    }
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place, items.length, subOpen]); // an inline submenu changes the menu's height

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
      if (!["ArrowDown", "ArrowUp", "Home", "End", "ArrowRight", "ArrowLeft"].includes(event.key)) return;
      const active = document.activeElement;
      const inSub = Boolean(active?.closest?.("[data-submenu]"));
      if (event.key === "ArrowRight") {
        const parentKey = active?.getAttribute?.("data-parent");
        if (!parentKey) return;
        event.preventDefault();
        openSub(parentKey, true);
        return;
      }
      if (event.key === "ArrowLeft") {
        if (!inSub) return;
        event.preventDefault();
        const parentKey = active.closest("[data-submenu]").getAttribute("data-submenu");
        setSubOpen(null);
        menuRef.current?.querySelector(`[data-parent="${parentKey}"]`)?.focus();
        return;
      }
      // Up/Down/Home/End stay inside the submenu while focus is in it, else walk the top-level items.
      const scope = inSub ? active.closest("[data-submenu]") : menuRef.current;
      const entries = [...(scope?.querySelectorAll('[role="menuitem"]:not([disabled])') || [])].filter(
        (el) => inSub || !el.closest("[data-submenu]"),
      );
      if (!entries.length) return;
      event.preventDefault();
      const index = entries.indexOf(active);
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
  }, [open, close, openSub]);

  const stop = (event) => event.stopPropagation();

  const childClass = `${ITEM_CLASS} text-ink hover:bg-cream-100 focus-visible:bg-cream-100`;
  // Plain functions returning elements (not components) so focus survives re-renders.
  const renderChild = (child) =>
    child.href ? (
      <a key={child.key} role="menuitem" href={child.href} onClick={() => close(false)} className={childClass}>
        <span className="truncate">{child.label}</span>
      </a>
    ) : (
      <button
        key={child.key}
        type="button"
        role="menuitem"
        onClick={() => {
          close(false);
          child.onSelect?.();
        }}
        className={childClass}
      >
        <span className="truncate">{child.label}</span>
      </button>
    );

  const renderParent = (item) => {
    const expanded = subOpen === item.key;
    const flyout = position.flyout;
    return (
      <div
        className="relative"
        onMouseEnter={() => flyout && openSub(item.key)}
        onMouseLeave={() => flyout && setSubOpen((current) => (current === item.key ? null : current))}
      >
        <button
          type="button"
          role="menuitem"
          data-parent={item.key}
          aria-haspopup="menu"
          aria-expanded={expanded}
          onClick={(event) => {
            // Flyout: a click keeps it open (hover may already have). Inline: a tap toggles.
            if (flyout) openSub(item.key, event.detail === 0);
            else if (expanded) setSubOpen(null);
            else openSub(item.key, event.detail === 0);
          }}
          className={`${ITEM_CLASS} text-ink hover:bg-cream-100 focus-visible:bg-cream-100 ${expanded ? "bg-cream-100" : ""}`}
        >
          <span className="truncate">{item.label}</span>
          <svg
            className={`h-3.5 w-3.5 shrink-0 text-muted transition-transform ${!flyout && expanded ? "rotate-90" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
        {expanded && (
          <div
            role="menu"
            aria-label={item.label}
            data-submenu={item.key}
            style={flyout ? { width: MENU_WIDTH } : undefined}
            className={
              flyout
                ? `absolute ${flyUp ? "bottom-0" : "top-0"} ${flyout === "right" ? "left-full" : "right-full"} rounded-xl border border-cream-200 bg-surface-light py-1.5 shadow-xl`
                : "border-y border-cream-200 bg-cream-100/60 py-1 pl-4"
            }
          >
            {item.children.map(renderChild)}
          </div>
        )}
      </div>
    );
  };

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
            className="rounded-xl border border-cream-200 bg-surface-light py-1.5 shadow-xl"
            onClick={stop}
            onMouseDown={stop}
          >
            {items.map((item) => (
              <div key={item.key}>
                {item.divider && <div className="my-1 border-t border-cream-200" role="separator" />}
                {item.children ? (
                  renderParent(item)
                ) : (
                  <button
                    type="button"
                    role="menuitem"
                    disabled={item.disabled}
                    onClick={() => {
                      close(false);
                      item.onSelect?.();
                    }}
                    className={`${ITEM_CLASS} ${
                      item.danger
                        ? "text-red-600 hover:bg-red-50 focus-visible:bg-red-50"
                        : "text-ink hover:bg-cream-100 focus-visible:bg-cream-100"
                    }`}
                  >
                    <span className="truncate">{item.label}</span>
                    {item.hint && <span className="shrink-0 text-[10px] text-muted">{item.hint}</span>}
                  </button>
                )}
              </div>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
