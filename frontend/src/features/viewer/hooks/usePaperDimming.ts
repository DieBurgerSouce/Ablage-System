import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { CSSProperties } from 'react';

type DimmingLevel = 'light' | 'medium' | 'strong' | 'custom';

interface PaperDimmingState {
    enabled: boolean;
    level: DimmingLevel;
    brightness: number; // 0.4-1.0 (default 0.85)
    contrast: number; // 0.8-1.2 (default 1.1)
    sepia: boolean; // warm light option
    autoActivate: boolean; // auto-enable in dark/blackscreen modes
    // Actions
    setEnabled: (enabled: boolean) => void;
    setLevel: (level: DimmingLevel) => void;
    setBrightness: (brightness: number) => void;
    setContrast: (contrast: number) => void;
    setSepia: (sepia: boolean) => void;
    setAutoActivate: (auto: boolean) => void;
    getFilterStyle: () => CSSProperties;
}

export const usePaperDimming = create<PaperDimmingState>()(
    persist(
        (set, get) => ({
            enabled: false,
            level: 'light',
            brightness: 0.85,
            contrast: 1.1,
            sepia: false,
            autoActivate: false,
            setEnabled: (enabled) => set({ enabled }),
            setLevel: (level) => {
                // When setting a preset level, update brightness and contrast
                if (level === 'light') {
                    set({ level, brightness: 0.85, contrast: 1.05 });
                } else if (level === 'medium') {
                    set({ level, brightness: 0.70, contrast: 1.10 });
                } else if (level === 'strong') {
                    set({ level, brightness: 0.55, contrast: 1.15 });
                } else {
                    set({ level });
                }
            },
            setBrightness: (brightness) => set({ brightness, level: 'custom' }),
            setContrast: (contrast) => set({ contrast, level: 'custom' }),
            setSepia: (sepia) => set({ sepia }),
            setAutoActivate: (autoActivate) => set({ autoActivate }),
            getFilterStyle: () => {
                const state = get();
                if (!state.enabled) {
                    return {};
                }

                let filterValue = '';

                if (state.level === 'light') {
                    filterValue = 'brightness(0.85) contrast(1.05)';
                } else if (state.level === 'medium') {
                    filterValue = 'brightness(0.70) contrast(1.10)';
                } else if (state.level === 'strong') {
                    filterValue = 'brightness(0.55) contrast(1.15)';
                } else {
                    // custom
                    filterValue = `brightness(${state.brightness}) contrast(${state.contrast})`;
                }

                if (state.sepia) {
                    filterValue += ' sepia(0.3)';
                }

                return { filter: filterValue };
            },
        }),
        {
            name: 'ablage-paper-dimming',
            partialize: (state) => ({
                enabled: state.enabled,
                level: state.level,
                brightness: state.brightness,
                contrast: state.contrast,
                sepia: state.sepia,
                autoActivate: state.autoActivate,
            }),
        }
    )
);
