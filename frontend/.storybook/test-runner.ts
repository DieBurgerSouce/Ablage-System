/**
 * Storybook Test Runner Konfiguration
 *
 * Fuehrt Tests fuer alle Stories aus:
 * - Accessibility Tests (axe)
 * - Interaction Tests
 * - Screenshot Comparison (optional)
 *
 * Ausfuehrung: npm run test:storybook
 */

import type { TestRunnerConfig } from '@storybook/test-runner';
import { checkA11y, injectAxe } from 'axe-playwright';

const config: TestRunnerConfig = {
    /**
     * Hook: Wird vor jedem Test ausgefuehrt
     * Injiziert die axe-core Library fuer A11y Tests
     */
    async preVisit(page) {
        await injectAxe(page);
    },

    /**
     * Hook: Wird nach jedem Test ausgefuehrt
     * Fuehrt Accessibility-Pruefungen durch
     */
    async postVisit(page, context) {
        // A11y Check mit axe
        await checkA11y(page, '#storybook-root', {
            detailedReport: true,
            detailedReportOptions: {
                html: true,
            },
            // axe Konfiguration
            axeOptions: {
                runOnly: {
                    type: 'tag',
                    values: [
                        'wcag2a',      // WCAG 2.0 Level A
                        'wcag2aa',     // WCAG 2.0 Level AA
                        'wcag21a',     // WCAG 2.1 Level A
                        'wcag21aa',    // WCAG 2.1 Level AA
                        'best-practice',
                    ],
                },
                rules: {
                    // Spezifische Regeln anpassen wenn noetig
                    'color-contrast': { enabled: true },
                    'html-has-lang': { enabled: false }, // Storybook setzt kein lang
                    'landmark-one-main': { enabled: false }, // Stories haben kein main
                    'region': { enabled: false }, // Stories haben keine Regions
                },
            },
        });
    },

    /**
     * Tags die getestet werden sollen
     * Stories mit 'skip' Tag werden uebersprungen
     */
    tags: {
        skip: ['skip-test', 'no-test'],
        include: [],
        exclude: [],
    },

    /**
     * Test Timeout in Millisekunden
     */
    testTimeout: 15000,

    /**
     * Parallele Ausfuehrung
     */
    maxWorkers: 4,

    /**
     * Browser Einstellungen
     */
    launchOptions: {
        headless: true,
    },
};

export default config;
