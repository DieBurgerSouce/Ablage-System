/**
 * Percy Konfiguration fuer Visual Regression Testing
 *
 * Percy nimmt automatisch Snapshots von Storybook Stories
 * und vergleicht sie mit der Baseline.
 *
 * Dokumentation: https://docs.percy.io/docs/storybook
 */

module.exports = {
    version: 2,

    // Storybook-spezifische Konfiguration
    storybook: {
        // Welche Stories sollen getestet werden?
        // Nutzt Storybook-Glob-Pattern
        include: [
            'UI/**',      // Alle UI-Komponenten
            'Forms/**',   // Alle Formular-Komponenten
            'Charts/**',  // Alle Chart-Komponenten
        ],

        // Stories die ausgeschlossen werden sollen
        exclude: [
            '**/DarkMode',           // Dark Mode separat testen
            '**/*Loading*',          // Loading States haben Animationen
            '**/*Controlled*',       // Controlled Components brauchen Interaktion
        ],

        // Globale Argumente fuer alle Stories
        args: {},
    },

    // Snapshot Konfiguration
    snapshot: {
        // Responsive Breakpoints fuer Visual Testing
        widths: [375, 768, 1280, 1920],

        // Minimum Hoehe fuer Snapshots
        minHeight: 1024,

        // Percy CSS wird in jeden Snapshot injiziert
        // Nuetzlich um Animationen zu deaktivieren
        percyCSS: `
            /* Deaktiviere Animationen fuer konsistente Snapshots */
            *, *::before, *::after {
                animation-duration: 0s !important;
                animation-delay: 0s !important;
                transition-duration: 0s !important;
                transition-delay: 0s !important;
            }

            /* Scrollbars standardisieren */
            ::-webkit-scrollbar {
                width: 0px !important;
                height: 0px !important;
            }

            /* Cursor verstecken */
            * {
                cursor: none !important;
            }

            /* Fokus-Ring deaktivieren (konsistenter) */
            *:focus {
                outline: none !important;
            }
        `,

        // Warte auf diesen Selector bevor Snapshot gemacht wird
        waitForSelector: '.sb-show-main',

        // Timeout fuer Seiten-Rendering (ms)
        waitForTimeout: 1000,

        // JavaScript ausfuehren bevor Snapshot gemacht wird
        enableJavaScript: true,
    },

    // Discovery Konfiguration (URL-Erkennung)
    discovery: {
        // Timeout fuer Asset-Discovery (ms)
        networkIdleTimeout: 100,

        // Concurrent Browser Sessions
        concurrency: 10,

        // Warte bis Netzwerk idle ist
        waitForTimeout: 5000,

        // Externe Ressourcen erlauben
        allowedHostnames: [
            'fonts.googleapis.com',
            'fonts.gstatic.com',
        ],
    },

    // Upload Konfiguration
    upload: {
        // Parallel uploads
        concurrency: 20,
    },
};
