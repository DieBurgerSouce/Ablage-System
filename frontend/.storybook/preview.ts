/**
 * Storybook Preview Konfiguration
 *
 * Globale Dekoratoren, Parameter und Theme-Konfiguration
 * fuer alle Stories im Ablage-System.
 */

import type { Preview } from '@storybook/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Import global styles
import '../src/index.css';

// Create a QueryClient for stories
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            retry: false,
            staleTime: Infinity,
        },
    },
});

/**
 * Theme Provider Decorator
 * Wraps stories with theme context (dark/light mode)
 */
const withThemeProvider = (Story: React.ComponentType, context: { globals: { theme: string } }) => {
    const theme = context.globals.theme || 'light';

    React.useEffect(() => {
        const root = document.documentElement;
        root.classList.remove('light', 'dark');
        root.classList.add(theme);
    }, [theme]);

    return React.createElement(
        'div',
        { className: `theme-${theme}` },
        React.createElement(Story)
    );
};

/**
 * QueryClient Provider Decorator
 * Wraps stories with TanStack Query context
 */
const withQueryClient = (Story: React.ComponentType) => {
    return React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(Story)
    );
};

/**
 * Container Decorator
 * Provides consistent padding and background for stories
 */
const withContainer = (Story: React.ComponentType) => {
    return React.createElement(
        'div',
        { className: 'p-4 min-h-screen bg-background' },
        React.createElement(Story)
    );
};

const preview: Preview = {
    parameters: {
        actions: { argTypesRegex: '^on[A-Z].*' },
        controls: {
            matchers: {
                color: /(background|color)$/i,
                date: /Date$/i,
            },
        },
        backgrounds: {
            default: 'light',
            values: [
                { name: 'light', value: '#ffffff' },
                { name: 'dark', value: '#0a0a0a' },
                { name: 'gray', value: '#f5f5f5' },
            ],
        },
        viewport: {
            viewports: {
                mobile: {
                    name: 'Mobile',
                    styles: {
                        width: '375px',
                        height: '667px',
                    },
                },
                tablet: {
                    name: 'Tablet',
                    styles: {
                        width: '768px',
                        height: '1024px',
                    },
                },
                desktop: {
                    name: 'Desktop',
                    styles: {
                        width: '1280px',
                        height: '800px',
                    },
                },
                widescreen: {
                    name: 'Widescreen',
                    styles: {
                        width: '1920px',
                        height: '1080px',
                    },
                },
            },
        },
        layout: 'centered',
        docs: {
            toc: true,
        },
        // A11y addon configuration
        a11y: {
            config: {
                rules: [
                    {
                        id: 'color-contrast',
                        enabled: true,
                    },
                ],
            },
        },
    },

    globalTypes: {
        theme: {
            description: 'Farbschema',
            defaultValue: 'light',
            toolbar: {
                title: 'Theme',
                icon: 'paintbrush',
                items: [
                    { value: 'light', icon: 'sun', title: 'Hell' },
                    { value: 'dark', icon: 'moon', title: 'Dunkel' },
                ],
                dynamicTitle: true,
            },
        },
        locale: {
            description: 'Sprache',
            defaultValue: 'de',
            toolbar: {
                title: 'Locale',
                icon: 'globe',
                items: [
                    { value: 'de', title: 'Deutsch' },
                    { value: 'en', title: 'English' },
                ],
            },
        },
    },

    decorators: [withContainer, withQueryClient, withThemeProvider],

    tags: ['autodocs'],
};

export default preview;
