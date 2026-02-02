/**
 * Storybook Manager Konfiguration
 *
 * Konfiguriert das Storybook UI Theme und Branding
 * fuer das Ablage-System.
 */

import { addons } from '@storybook/manager-api';
import { create } from '@storybook/theming/create';

const ablageTheme = create({
    base: 'light',

    // Brand
    brandTitle: 'Ablage-System UI',
    brandUrl: '/',
    brandTarget: '_self',

    // UI
    appBg: '#f8fafc',
    appContentBg: '#ffffff',
    appPreviewBg: '#ffffff',
    appBorderColor: '#e2e8f0',
    appBorderRadius: 8,

    // Typography
    fontBase: '"Inter", "Segoe UI", "Helvetica Neue", sans-serif',
    fontCode: '"JetBrains Mono", "Fira Code", monospace',

    // Text colors
    textColor: '#0f172a',
    textInverseColor: '#f8fafc',
    textMutedColor: '#64748b',

    // Toolbar default and active colors
    barTextColor: '#64748b',
    barSelectedColor: '#2563eb',
    barHoverColor: '#1e40af',
    barBg: '#ffffff',

    // Form colors
    inputBg: '#ffffff',
    inputBorder: '#e2e8f0',
    inputTextColor: '#0f172a',
    inputBorderRadius: 6,

    // Button colors
    buttonBg: '#f1f5f9',
    buttonBorder: '#e2e8f0',

    // Boolean colors
    booleanBg: '#e2e8f0',
    booleanSelectedBg: '#2563eb',

    // Color palette
    colorPrimary: '#2563eb',
    colorSecondary: '#64748b',
});

addons.setConfig({
    theme: ablageTheme,
    sidebar: {
        showRoots: true,
        collapsedRoots: ['other'],
    },
    toolbar: {
        title: { hidden: false },
        zoom: { hidden: false },
        eject: { hidden: false },
        copy: { hidden: false },
        fullscreen: { hidden: false },
    },
    enableShortcuts: true,
    showNav: true,
    showPanel: true,
    panelPosition: 'bottom',
    initialActive: 'sidebar',
});
