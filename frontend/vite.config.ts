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
        // W2.3 (2026-07): Precache NUR auf die App-Shell begrenzt.
        // Vorher precachte `**/*.{js,...}` ALLE Build-Chunks — inkl. der ~300
        // lazy-geladenen Route-/Komponenten-Chunks (der Entry-Chunk allein ~7 MiB).
        // Jeder frische Browser-Context mit SW-Registrierung zog damit das
        // KOMPLETTE Bundle-Set durch nginx; unter 4 parallelen Playwright-Workern
        // fuehrte das zu Chromium-Ressourcen-Starvation (browserContext.newPage-
        // Timeout im pwa-offline-Fixture, A-Z-Loop 7). Jetzt precachen wir nur die
        // zum Offline-Boot noetigen Dateien: index.html, Offline-Fallback, den
        // Entry-Chunk (`index-*.js`), den React-Vendor-Chunk, das App-CSS und
        // Fonts. Die Route-Chunks werden stattdessen zur LAUFZEIT per
        // runtimeCaching (CacheFirst 'app-chunks', s.u.) gecacht.
        // Trade-off (bewusst akzeptiert): Eine noch NICHT besuchte Route ist
        // offline erst nach ihrem ersten Online-Aufruf verfuegbar — die App-Shell
        // selbst bleibt aber voll offline-faehig. 300 Chunks vorab zu cachen ist
        // weder noetig noch (Bandbreite/Install-Zeit) vertretbar.
        globPatterns: [
          'index.html',
          'offline.html',
          'assets/index-*.js',        // Entry-Chunk (App-Shell-Einstieg)
          'assets/react-vendor-*.js', // React-Runtime-Vendor-Chunk
          'assets/*.css',             // App-CSS (gebuendelt)
          'fonts/*.{woff,woff2}',
        ],
        maximumFileSizeToCacheInBytes: 8 * 1024 * 1024, // 8 MiB — deckt den grossen Entry-Chunk ab
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
            // W2.3: Route-/Komponenten-Chunks (lazy geladen, NICHT in der
            // Precache-Shell). CacheFirst, weil content-gehashte Chunks
            // immutabel sind (die URL aendert sich bei Inhaltsaenderung) — so
            // bleibt eine einmal besuchte Route offline verfuegbar, ohne bei
            // jedem Aufruf zu revalidieren. Precachte Shell-Chunks (index-*.js,
            // react-vendor-*.js, *.css) treffen diese Regel nicht: fuer sie
            // greift die Precache-Route vorrangig.
            urlPattern: /\/assets\/.*\.(?:js|css)$/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'app-chunks',
              expiration: {
                maxEntries: 300, // deckt alle lazy Route-Chunks ab
                maxAgeSeconds: 60 * 60 * 24 * 30, // 30 Tage
              },
              cacheableResponse: {
                statuses: [0, 200],
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
