/**
 * B7-Regression: Lazy-Routen unter AnimatePresence mode="wait"
 *
 * Reproduziert die Struktur aus __root.tsx:
 *   <AnimatePresence mode="wait">
 *     <motion.div key={pathname} {...pageTransition}>
 *       <Outlet/>  -> Routenkomponente mit eigenem <Suspense> + React.lazy
 *     </motion.div>
 *   </AnimatePresence>
 *
 * TanStack Router fuehrt Navigationen in einer React-Transition aus
 * (startTransition). Erwartung: Nach Aufloesen des Lazy-Chunks MUSS die
 * Zielkomponente mounten - der Suspense-Spinner darf nicht haengen bleiben.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import {
  lazy,
  Suspense,
  startTransition,
  useState,
  type ComponentType,
} from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
  useLocation,
} from '@tanstack/react-router';
import { pageTransition } from '@/lib/animations';

// ==================== Helpers ====================

function makeControlledLazy() {
  let resolveModule!: (m: { default: ComponentType }) => void;
  const modulePromise = new Promise<{ default: ComponentType }>((resolve) => {
    resolveModule = resolve;
  });
  const LazyComp = lazy(() => modulePromise);
  return { LazyComp, resolveModule };
}

/**
 * Nachbau der __root.tsx-Seitenuebergangs-Struktur.
 * `navigateRef` erhaelt eine navigate-Funktion, die wie TanStack Router
 * den Pfadwechsel in startTransition ausfuehrt.
 */
function Shell({
  LazyComp,
  navigateRef,
}: {
  LazyComp: ComponentType;
  navigateRef: { current: ((path: string) => void) | null };
}) {
  const [path, setPath] = useState('/a');
  navigateRef.current = (next: string) => {
    startTransition(() => setPath(next));
  };

  return (
    <AnimatePresence mode="wait">
      <motion.div key={path} {...pageTransition}>
        {path === '/a' ? (
          <div>Seite A</div>
        ) : (
          <Suspense fallback={<div role="status">Spinner</div>}>
            <LazyComp />
          </Suspense>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

// ==================== Tests ====================

describe('Lazy-Route unter AnimatePresence (B7)', () => {
  it('mountet die Lazy-Zielroute nach Navigation + Chunk-Aufloesung', async () => {
    const { LazyComp, resolveModule } = makeControlledLazy();
    const navigateRef: { current: ((path: string) => void) | null } = {
      current: null,
    };

    render(<Shell LazyComp={LazyComp} navigateRef={navigateRef} />);
    expect(screen.getByText('Seite A')).toBeInTheDocument();

    // Navigation wie der Router: in einer React-Transition
    act(() => {
      navigateRef.current?.('/b');
    });

    // "Chunk" laedt fertig
    await act(async () => {
      resolveModule({ default: () => <div>Seite B</div> });
    });

    // Zielkomponente MUSS mounten (Exit-Animation 0.15s + Puffer)
    expect(
      await screen.findByText('Seite B', undefined, { timeout: 4000 })
    ).toBeInTheDocument();
  });

  it('mountet die Lazy-Zielroute mit ECHTEM Router-Outlet (originalgetreue __root-Struktur)', async () => {
    // Originalgetreuer Nachbau: Der entscheidende Unterschied zum
    // vereinfachten Repro oben ist, dass das Kind der motion.div ein
    // <Outlet/> (Context-Consumer) ist. Nach der Navigation rendert auch
    // der von AnimatePresence festgehaltene EXIT-Klon (alter key) den
    // Outlet neu - und damit bereits die NEUE, suspendende Lazy-Route.
    const { LazyComp, resolveModule } = makeControlledLazy();

    function RootLayout() {
      const location = useLocation();
      return (
        <AnimatePresence mode="wait">
          <motion.div key={location.pathname} {...pageTransition}>
            <Outlet />
          </motion.div>
        </AnimatePresence>
      );
    }

    const rootRoute = createRootRoute({ component: RootLayout });
    const indexRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/',
      component: () => <div>Seite A</div>,
    });
    const uploadRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/upload',
      component: () => (
        <Suspense fallback={<div role="status">Spinner</div>}>
          <LazyComp />
        </Suspense>
      ),
    });

    const router = createRouter({
      routeTree: rootRoute.addChildren([indexRoute, uploadRoute]),
      history: createMemoryHistory({ initialEntries: ['/'] }),
    });

    render(<RouterProvider router={router} />);
    expect(await screen.findByText('Seite A')).toBeInTheDocument();

    // Navigation wie in der App (TanStack Router nutzt intern Transitions)
    await act(async () => {
      await router.navigate({ to: '/upload' });
    });

    // MECHANIK-NACHWEIS (B7): Der von AnimatePresence fuer die
    // Exit-Animation festgehaltene Klon (alter key '/') enthaelt einen
    // LIVE <Outlet/> (Context-Consumer). Direkt nach der Navigation rendert
    // deshalb auch der "alte" Baum bereits die NEUE Route - die
    // Exit-Animation zeigt also nie den alten Seiteninhalt, sondern den
    // Suspense-Spinner der Zielroute. Genau diese Verschraenkung
    // (suspendierender Exit-Klon x mode="wait"-Buchhaltung) ist der
    // Naehrboden des Dauer-Spinners im Browser.
    expect(screen.queryByText('Seite A')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();

    // "Chunk" laedt fertig
    await act(async () => {
      resolveModule({ default: () => <div>Seite B</div> });
    });

    // Zielkomponente MUSS mounten - Dauer-Spinner ist der B7-Bug
    expect(
      await screen.findByText('Seite B', undefined, { timeout: 4000 })
    ).toBeInTheDocument();
  });

  it('FIX-Struktur (__root ohne AnimatePresence): Lazy-Zielroute mountet, Enter-Animation bleibt', async () => {
    // Regressionstest fuer den B7-Fix: keyed motion.div OHNE AnimatePresence.
    // Kein Exit-Klon -> kein suspendierender Alt-Baum -> keine
    // mode="wait"-Buchhaltung, die im Browser haengen bleiben kann.
    const { LazyComp, resolveModule } = makeControlledLazy();

    function RootLayout() {
      const location = useLocation();
      return (
        <motion.div key={location.pathname} {...pageTransition}>
          <Outlet />
        </motion.div>
      );
    }

    const rootRoute = createRootRoute({ component: RootLayout });
    const indexRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/',
      component: () => <div>Seite A</div>,
    });
    const uploadRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/upload',
      component: () => (
        <Suspense fallback={<div role="status">Spinner</div>}>
          <LazyComp />
        </Suspense>
      ),
    });

    const router = createRouter({
      routeTree: rootRoute.addChildren([indexRoute, uploadRoute]),
      history: createMemoryHistory({ initialEntries: ['/'] }),
    });

    render(<RouterProvider router={router} />);
    expect(await screen.findByText('Seite A')).toBeInTheDocument();

    await act(async () => {
      await router.navigate({ to: '/upload' });
    });

    // Waehrend der Chunk laedt: Suspense-Fallback sichtbar
    expect(screen.getByRole('status')).toBeInTheDocument();

    await act(async () => {
      resolveModule({ default: () => <div>Seite B</div> });
    });

    expect(
      await screen.findByText('Seite B', undefined, { timeout: 4000 })
    ).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('mountet eine Lazy-Route auch beim Direkteinstieg (ohne Navigation)', async () => {
    const { LazyComp, resolveModule } = makeControlledLazy();

    render(
      <AnimatePresence mode="wait">
        <motion.div key="/b" {...pageTransition}>
          <Suspense fallback={<div role="status">Spinner</div>}>
            <LazyComp />
          </Suspense>
        </motion.div>
      </AnimatePresence>
    );

    expect(screen.getByRole('status')).toBeInTheDocument();

    await act(async () => {
      resolveModule({ default: () => <div>Seite B</div> });
    });

    expect(
      await screen.findByText('Seite B', undefined, { timeout: 4000 })
    ).toBeInTheDocument();
  });
});
