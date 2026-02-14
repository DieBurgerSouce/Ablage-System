/**
 * Vitest Test Setup
 *
 * Konfiguriert React Testing Library, jsdom, cleanup und custom matchers
 */

import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Cleanup nach jedem Test (verhindert Memory Leaks)
afterEach(() => {
  cleanup();
});

// Mock für window.matchMedia (fuer Radix UI Components)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock für ResizeObserver (fuer Radix UI Dialog/Popover)
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock für IntersectionObserver (fuer Scroll-basierte Components)
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
};

// Mock für PointerEvent (fuer DnD Components)
class PointerEvent extends Event {
  constructor(type: string, params: PointerEventInit = {}) {
    super(type, params);
  }
}
global.PointerEvent = PointerEvent as any;

// Mock fuer scrollIntoView (oft in Tests genutzt)
Element.prototype.scrollIntoView = () => {};
