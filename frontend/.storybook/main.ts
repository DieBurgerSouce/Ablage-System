/**
 * Storybook Konfiguration fuer Ablage-System
 *
 * Konfiguriert Storybook 8.x fuer React + Vite + TypeScript
 * mit Addons fuer Accessibility, Interactions und Visual Testing.
 */

import type { StorybookConfig } from '@storybook/react-vite';
import { mergeConfig } from 'vite';
import path from 'path';

const config: StorybookConfig = {
    stories: [
        '../src/stories/**/*.mdx',
        '../src/stories/**/*.stories.@(js|jsx|mjs|ts|tsx)',
        '../src/components/**/*.stories.@(js|jsx|mjs|ts|tsx)',
    ],

    addons: [
        '@storybook/addon-essentials',
        '@storybook/addon-a11y',
        '@storybook/addon-interactions',
        '@storybook/addon-links',
        '@storybook/addon-coverage',
    ],

    framework: {
        name: '@storybook/react-vite',
        options: {},
    },

    docs: {
        autodocs: 'tag',
    },

    staticDirs: ['../public'],

    viteFinal: async (config) => {
        return mergeConfig(config, {
            resolve: {
                alias: {
                    '@': path.resolve(__dirname, '../src'),
                },
            },
            // Ensure CSS is properly handled
            css: {
                postcss: {
                    plugins: [],
                },
            },
        });
    },

    typescript: {
        reactDocgen: 'react-docgen-typescript',
        reactDocgenTypescriptOptions: {
            shouldExtractLiteralValuesFromEnum: true,
            propFilter: (prop) =>
                prop.parent ? !/node_modules/.test(prop.parent.fileName) : true,
        },
    },
};

export default config;
