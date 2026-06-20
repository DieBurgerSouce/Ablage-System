import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    test: {
        environment: 'happy-dom',
        setupFiles: ['./src/test/setup.ts'],
        globals: true,
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
        css: true,
        // Windows: parallele Datei-Worker haengen (jsdom/happy-dom-Worker,
        // 1360s/"no tests" — siehe RECENT_CHANGES 2026-06-09). Seriell ist stabil.
        fileParallelism: false,
    },
})
