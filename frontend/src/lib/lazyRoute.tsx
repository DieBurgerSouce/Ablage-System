import { useEffect, useRef, useState, type ComponentType, type ReactElement } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'
import { logger } from '@/lib/logger'

/**
 * B7 (2026-06-13): Robuster Ersatz fuer `React.lazy` + `<Suspense>` bei
 * Route-Code-Splitting.
 *
 * BEFUND (Production-Build, instrumentiert + per Playwright gegen `vite preview`
 * verifiziert): `React.lazy(() => import(...))` mit umgebendem `<Suspense>`
 * blieb im GEBAUTEN Bundle (React 19.2) bei ALLEN ~25 Code-Split-Routen
 * (/upload, /admin/banking/*, /command-center, /agent-chat u.v.m.) dauerhaft im
 * LazyLoadFallback-Spinner haengen. Nachgewiesen:
 *   1. Der Lazy-Chunk wird geladen (Network: 200/FINISHED), KEIN Fehler,
 *      KEINE Promise-Rejection.
 *   2. Die Lazy-Factory wird aufgerufen UND resolved mit einer gueltigen
 *      Komponenten-Funktion (console: "lazy factory RESOLVED, has X=function").
 *   3. ABER React rendert die Suspense-Boundary nie erneut -> die Boundary
 *      wird nach dem Resolve nie "gepingt" -> der Fallback bleibt stehen.
 *   4. Ein DIREKTER (nicht-lazy) Import derselben Komponente rendert sofort;
 *      ein manueller `import().then(setState)` rendert ebenfalls sofort.
 * Im Dev-Server tritt das nicht auf (dort wird nicht gechunkt). Die Ursache ist
 * also der `React.lazy`-Ping-Mechanismus im Production-Bundle, NICHT die
 * Komponente, das Chunking, der Service-Worker oder framer-motion (alle vier
 * per Build-Variante einzeln ausgeschlossen).
 *
 * FIX: Statt auf Reacts impliziten Suspense-Ping zu vertrauen, fuehren wir den
 * dynamischen Import selbst aus und erzwingen das Re-Render ueber `setState` -
 * derselbe Mechanismus, der in der Verifikation zuverlaessig gerendert hat.
 * API-kompatibel zum bisherigen Muster:
 *
 *   const UploadWizard = lazyRoute(() => import('...').then(m => ({ default: m.UploadWizard })))
 *   // render: <UploadWizard />   (KEIN umgebendes <Suspense> noetig)
 *
 * Es ist KEIN <Suspense> mehr noetig; der Fallback ist eingebaut und kann per
 * `fallback`-Option ueberschrieben werden.
 */

// Loader wie bei React.lazy: ein dynamischer Import, der auf ein Modul mit
// `default`-Export einer Komponente aufloest. Der Komponenten-Prop-Typ wird
// bewusst breit gehalten (`ComponentType<any>`), damit propslose
// Routenkomponenten (`() => Element`) und solche mit Props gleichermassen ohne
// Varianz-Konflikt unifizieren - das oeffentliche Verhalten bleibt unveraendert,
// da Routenkomponenten ohnehin ohne Props gerendert werden.
type Loader = () => Promise<{ default: ComponentType<AnyProps> }>
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyProps = any

interface LazyRouteOptions {
    /** Eigener Ladezustand statt des Standard-Spinners. */
    fallback?: ReactElement | null
}

export function lazyRoute(
    loader: Loader,
    options: LazyRouteOptions = {},
): ComponentType {
    const fallback = options.fallback ?? <LazyLoadFallback />

    // Modul-Promise EINMAL pro lazyRoute()-Aufruf cachen, damit der Chunk bei
    // Re-Mounts/mehrfachem Rendern nur einmal geladen wird und alle Instanzen
    // dasselbe (ggf. bereits aufgeloeste) Promise teilen.
    let modulePromise: Promise<{ default: ComponentType<AnyProps> }> | null = null
    function load() {
        if (!modulePromise) modulePromise = loader()
        return modulePromise
    }

    function LazyRouteComponent(props: AnyProps) {
        const [Component, setComponent] = useState<ComponentType<AnyProps> | null>(null)
        const [failed, setFailed] = useState(false)
        const mountedRef = useRef(true)

        useEffect(() => {
            mountedRef.current = true
            let cancelled = false
            load()
                .then((mod) => {
                    if (cancelled || !mountedRef.current) return
                    // Funktion in den State: useState-Updater wuerde sie sonst aufrufen.
                    setComponent(() => mod.default)
                })
                .catch((err) => {
                    logger.error('[lazyRoute] Chunk konnte nicht geladen werden', err)
                    if (!cancelled && mountedRef.current) setFailed(true)
                })
            return () => {
                cancelled = true
                mountedRef.current = false
            }
        }, [])

        if (failed) {
            return (
                <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
                    <p className="text-sm text-muted-foreground">
                        Dieser Bereich konnte nicht geladen werden.
                    </p>
                    <button
                        type="button"
                        onClick={() => window.location.reload()}
                        className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
                    >
                        Seite neu laden
                    </button>
                </div>
            )
        }

        if (!Component) return fallback
        return <Component {...props} />
    }

    LazyRouteComponent.displayName = 'LazyRoute'
    return LazyRouteComponent
}
