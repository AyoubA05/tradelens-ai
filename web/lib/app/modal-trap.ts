"use client";

import { useEffect } from "react";
import type { RefObject } from "react";

/**
 * The behaviour every full-screen overlay in the app shell needs to actually
 * be a modal, not just look like one.
 *
 * Three hand-rolled versions of this existed in the branch before this file
 * did — the AI partner drawer had one, the period lens had a lighter
 * Escape-only version, and the More sheet had none of it despite being a
 * full-screen overlay. This is the one copy the drawer and the More sheet
 * both call.
 *
 * On open: focus moves into the panel (to `initialFocusRef` if given,
 * otherwise the panel itself), every top-level sibling of `rootRef` is
 * marked `inert` so a screen reader's browse mode cannot wander behind the
 * overlay, and Tab is trapped inside `panelRef`. Escape and closing both
 * ways call `onClose`. On close, `inert` is released and focus returns to
 * whatever had it before the modal opened — the one part of the contract
 * neither prior copy implemented.
 */
export function useModalTrap({
  open,
  onClose,
  rootRef,
  panelRef,
  initialFocusRef,
}: {
  open: boolean;
  onClose: () => void;
  rootRef: RefObject<HTMLElement | null>;
  panelRef: RefObject<HTMLElement | null>;
  initialFocusRef?: RefObject<HTMLElement | null>;
}) {
  useEffect(() => {
    if (!open) return;

    // Captured once per open, in this closure, so the cleanup below can send
    // focus back to it regardless of what else changes focus in between.
    const previouslyFocused = document.activeElement as HTMLElement | null;
    (initialFocusRef?.current ?? panelRef.current)?.focus();

    // aria-modal on the panel is a promise that nothing outside it is
    // reachable. Tab is trapped below, but a screen reader's browse mode (as
    // opposed to its focus/forms mode) ignores tab order and can still walk
    // into the page behind the overlay, so the promise needs the DOM to back
    // it up: every sibling of the overlay is marked inert while it is open,
    // and released when it closes.
    const root = rootRef.current;
    const siblings: HTMLElement[] = [];
    if (root?.parentElement) {
      for (const child of Array.from(root.parentElement.children)) {
        if (child === root || !(child instanceof HTMLElement)) continue;
        // Set the attribute directly rather than the `.inert` IDL property:
        // real browsers keep both in sync, but jsdom (as used in tests) does
        // not yet implement the property, only the attribute.
        child.setAttribute("inert", "");
        siblings.push(child);
      }
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      // Focus stays inside a modal surface. Without this, Tab walks into the
      // page behind the overlay, which a sighted user cannot see and a
      // screen reader user cannot escape from.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) {
        // Unreachable while the panel always renders at least one control,
        // but if it is ever emptied out, an unguarded Tab would walk
        // straight into the page behind the overlay. Keep focus pinned to
        // the panel itself instead.
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      for (const sibling of siblings) sibling.removeAttribute("inert");
      // Focus returns to whatever opened the modal, so a keyboard user is
      // not dropped onto <body> and left to find their place in the page
      // again.
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onClose/refs
    // are recreated by the caller on every render; re-running this effect on
    // every one of those would refocus the panel and re-walk the sibling
    // list for no reason. `open` is the only transition that matters here.
  }, [open]);
}
