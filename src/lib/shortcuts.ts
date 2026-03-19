/**
 * Keyboard shortcut definitions and handler.
 *
 * Central registry for all keyboard shortcuts in the app.
 * Works with the Svelte `use:shortcut` action pattern.
 */

export interface ShortcutDef {
  key: string;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  ctrl?: boolean;
  action: () => void;
  description: string;
}

/**
 * Check if a keyboard event matches a shortcut definition.
 */
function matches(event: KeyboardEvent, def: ShortcutDef): boolean {
  if (event.key.toLowerCase() !== def.key.toLowerCase()) return false;
  if (def.meta && !event.metaKey) return false;
  if (def.shift && !event.shiftKey) return false;
  if (def.alt && !event.altKey) return false;
  if (def.ctrl && !event.ctrlKey) return false;
  return true;
}

/**
 * Svelte action for attaching keyboard shortcuts to a node.
 *
 * Usage:
 *   <div use:shortcuts={myShortcuts}>
 */
export function shortcuts(node: HTMLElement, defs: ShortcutDef[]) {
  function handler(event: KeyboardEvent) {
    for (const def of defs) {
      if (matches(event, def)) {
        event.preventDefault();
        event.stopPropagation();
        def.action();
        return;
      }
    }
  }

  node.addEventListener("keydown", handler);

  return {
    update(newDefs: ShortcutDef[]) {
      defs = newDefs;
    },
    destroy() {
      node.removeEventListener("keydown", handler);
    },
  };
}

/**
 * App-wide shortcut definitions.
 *
 * These are created dynamically by components that register their
 * handlers via the callbacks object.
 */
export function createAppShortcuts(callbacks: {
  toggleSettings: () => void;
  clearSearch: () => void;
  focusSearch: () => void;
  selectNext: () => void;
  selectPrev: () => void;
  openSelected: () => void;
  revealSelected: () => void;
}): ShortcutDef[] {
  return [
    {
      key: ",",
      meta: true,
      action: callbacks.toggleSettings,
      description: "Open settings",
    },
    {
      key: "Escape",
      action: callbacks.clearSearch,
      description: "Clear search / close panel",
    },
    {
      key: "l",
      meta: true,
      action: callbacks.focusSearch,
      description: "Focus search bar",
    },
    {
      key: "ArrowDown",
      action: callbacks.selectNext,
      description: "Select next result",
    },
    {
      key: "ArrowUp",
      action: callbacks.selectPrev,
      description: "Select previous result",
    },
    {
      key: "Enter",
      action: callbacks.openSelected,
      description: "Open selected file",
    },
    {
      key: "Enter",
      meta: true,
      action: callbacks.revealSelected,
      description: "Reveal selected file in Finder",
    },
  ];
}

/**
 * Format a shortcut for display (e.g., "⌘,").
 */
export function formatShortcut(def: ShortcutDef): string {
  const parts: string[] = [];
  if (def.ctrl) parts.push("⌃");
  if (def.alt) parts.push("⌥");
  if (def.shift) parts.push("⇧");
  if (def.meta) parts.push("⌘");

  const keyMap: Record<string, string> = {
    ArrowUp: "↑",
    ArrowDown: "↓",
    ArrowLeft: "←",
    ArrowRight: "→",
    Enter: "↩",
    Escape: "⎋",
    " ": "Space",
    ",": ",",
  };

  parts.push(keyMap[def.key] || def.key.toUpperCase());
  return parts.join("");
}
