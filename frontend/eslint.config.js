import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // Verbiete direkte console.* Aufrufe - nutze stattdessen @/lib/logger
      'no-console': ['error', { allow: [] }],
    },
  },
  // Ausnahme fuer logger.ts - darf console.* verwenden
  {
    files: ['**/lib/logger.ts'],
    rules: {
      'no-console': 'off',
    },
  },
])
