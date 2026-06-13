import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    TanStackRouterVite({
      routesDirectory: "./src/app/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
    }),
    react(),
    VitePWA({
      registerType: 'prompt',
      injectRegister: 'auto',
      includeAssets: ['vite.svg', 'icons/*.png', 'icons/*.svg', 'screenshots/*.png'],
      manifest: false, // We use our own manifest.json
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
        maximumFileSizeToCacheInBytes: 8 * 1024 * 1024, // 8 MiB to accommodate large bundles
        // Enable navigation preload for faster page loads
        navigationPreload: true,
        runtimeCaching: [
          {
            // Cache API responses (NetworkFirst for fresh data)
            urlPattern: /^https?:\/\/.*\/api\/v1\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              networkTimeoutSeconds: 10,
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24, // 24 hours
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          {
            // Cache document/file downloads (CacheFirst - large files)
            urlPattern: /^https?:\/\/.*\/(documents|files|storage)\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'documents-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
              },
              cacheableResponse: {
                statuses: [0, 200],
              },
              rangeRequests: true,
            },
          },
          {
            // Cache images (CacheFirst)
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp)$/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'images-cache',
              expiration: {
                maxEntries: 100,
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
              },
            },
          },
          {
            // Cache fonts (CacheFirst - rarely change)
            urlPattern: /\.(?:woff|woff2|ttf|eot)$/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'fonts-cache',
              expiration: {
                maxEntries: 20,
                maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
              },
            },
          },
          {
            // StaleWhileRevalidate for static assets
            urlPattern: /\.(?:js|css)$/i,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'static-resources',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
              },
            },
          },
        ],
        cleanupOutdatedCaches: true,
        skipWaiting: true, // Force immediate update
        clientsClaim: true, // Take control immediately after activation
      },
      devOptions: {
        enabled: false, // Disable in development
        type: 'module',
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    // Generate source maps for debugging
    sourcemap: true,
    // Optimize chunk splitting
    rollupOptions: {
      output: {
        // B7-ROOT-CAUSE (2026-06-13): Die fruehere Objekt-Form
        //   manualChunks: { 'react-vendor': ['react', 'react-dom'], ... }
        // hat im Production-Build React FRAGMENTIERT: `react` (inkl.
        // ReactSharedInternals + jsx-runtime) landete in `react-vendor`,
        // waehrend `react-dom` (Reconciler + Scheduler) sowie `react/jsx-runtime`
        // anderer Module in den 6,5-MB-`index`-Chunk gezogen wurden. Ergebnis:
        // ZWEI Instanzen von `ReactSharedInternals` in zwei Chunks (per
        // `grep "SharedInternals"` in beiden nachweisbar). React.lazy registriert
        // sein Suspense-"Ping" ueber ReactSharedInternals; bei zwei Instanzen
        // pingt der geladene Lazy-Chunk eine ANDERE Internals-Instanz als die,
        // die der Reconciler beim Suspense-Boundary liest -> die Boundary wird
        // nie aufgeweckt -> ALLE 25 React.lazy-Routen (/upload,
        // /admin/banking/* u.a.) haengen im Production-Build dauerhaft im
        // LazyLoadFallback-Spinner (Chunk laedt, KEIN Fehler, KEINE Rejection;
        // ein DIREKTER, nicht-lazy Import derselben Komponente rendert sofort).
        // Im Dev-Server tritt das nicht auf, weil dort nicht gechunkt wird.
        // Fix: React-Runtime (react, react-dom, react/jsx-runtime, scheduler
        // und Reacts interne Pakete) MUSS in EINEM Chunk bleiben, damit es genau
        // EINE ReactSharedInternals-Instanz gibt. Funktion statt Objekt, weil das
        // Objekt-Format transitive react-dom-/jsx-runtime-Importe nicht zuverlaessig
        // demselben Chunk zuordnet.
        manualChunks(id: string) {
          // Die GESAMTE React-Runtime in EINEN Chunk: react, react-dom,
          // scheduler UND react/jsx-runtime. Nur so existiert genau eine
          // ReactSharedInternals-Instanz (siehe Kommentar oben). `react` muss
          // VOR `react-dom` geprueft werden; `react-dom` enthaelt den Reconciler,
          // `react` die Internals/jsx-runtime - beide gehoeren in denselben Chunk.
          // Wir splitten bewusst NUR React selbst manuell und ueberlassen den Rest
          // dem Rollup-Default, damit keine Chunk-Ladereihenfolge-/Zirkular-
          // Probleme entstehen (z.B. ein Vendor-Chunk, der `React.forwardRef`
          // referenziert, bevor der React-Chunk initialisiert ist).
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
            return 'react-vendor'
          }
          return undefined
        },
      },
    },
  },
})
