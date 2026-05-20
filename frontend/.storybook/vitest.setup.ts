/**
 * Vitest Setup fuer Storybook Tests
 *
 * Wird vor den Storybook Component Tests ausgefuehrt.
 * Konfiguriert Testing-Library und globale Mocks.
 */

import { beforeAll, afterAll, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Cleanup nach jedem Test
afterEach(() => {
    cleanup();
});

// Mock fuer window.matchMedia (fuer Theme-Detection)
beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: (query: string) => ({
            matches: false,
            media: query,
            onchange: null,
            addListener: () => {},
            removeListener: () => {},
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => false,
        }),
    });
});

// Mock fuer ResizeObserver
beforeAll(() => {
    global.ResizeObserver = class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
});

// Mock fuer IntersectionObserver
beforeAll(() => {
    global.IntersectionObserver = class IntersectionObserver {
        root = null;
        rootMargin = '';
        thresholds = [];

        observe() {}
        unobserve() {}
        disconnect() {}
        takeRecords() {
            return [];
        }
    };
});

// Mock fuer requestAnimationFrame
beforeAll(() => {
    global.requestAnimationFrame = (callback: FrameRequestCallback) => {
        return setTimeout(() => callback(Date.now()), 0);
    };
    global.cancelAnimationFrame = (id: number) => {
        clearTimeout(id);
    };
});

// Mock fuer crypto.randomUUID
beforeAll(() => {
    if (!global.crypto) {
        global.crypto = {} as Crypto;
    }
    if (!global.crypto.randomUUID) {
        global.crypto.randomUUID = () =>
            'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                const r = (Math.random() * 16) | 0;
                const v = c === 'x' ? r : (r & 0x3) | 0x8;
                return v.toString(16);
            });
    }
});

// Globale Error Handler
beforeAll(() => {
    // Unterdruecke React 18 Warnings in Tests
    const originalError = console.error;
    console.error = (...args: unknown[]) => {
        if (
            typeof args[0] === 'string' &&
            args[0].includes('Warning: ReactDOM.render is no longer supported')
        ) {
            return;
        }
        originalError.apply(console, args);
    };
});
