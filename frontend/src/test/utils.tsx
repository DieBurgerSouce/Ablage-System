/**
 * Test Utilities
 *
 * Render helpers mit Providers (QueryClient, Router mocks)
 */

import type { ReactElement, ReactNode } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createMemoryHistory, createRootRoute, createRouter } from '@tanstack/react-router';

// ============================================================================
// Query Client Setup
// ============================================================================

/**
 * Erstellt einen isolierten QueryClient für Tests
 * (verhindert cache pollution zwischen Tests)
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Keine Retries in Tests
        gcTime: 0, // Keine Cache-Persistierung
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// ============================================================================
// Test Router Setup
// ============================================================================

interface TestRouterOptions {
  initialPath?: string;
}

/**
 * Erstellt einen Test-Router mit Memory History
 */
export function createTestRouter(options: TestRouterOptions = {}) {
  const { initialPath = '/' } = options;

  const rootRoute = createRootRoute({
    component: () => <div>Root</div>,
  });

  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory({
      initialEntries: [initialPath],
    }),
  });

  return router;
}

// ============================================================================
// Custom Render Function
// ============================================================================

interface AllProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
  router?: ReturnType<typeof createTestRouter>;
}

/**
 * Wrapper mit allen Providers
 */
function AllProviders({ children, queryClient, router }: AllProvidersProps) {
  const testQueryClient = queryClient || createTestQueryClient();

  if (router) {
    return (
      <QueryClientProvider client={testQueryClient}>
        <RouterProvider router={router} />
        {children}
      </QueryClientProvider>
    );
  }

  return (
    <QueryClientProvider client={testQueryClient}>
      {children}
    </QueryClientProvider>
  );
}

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient;
  router?: ReturnType<typeof createTestRouter>;
}

/**
 * Custom render function mit Providers
 *
 * @example
 * ```tsx
 * const { getByText } = renderWithProviders(<MyComponent />);
 * ```
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: CustomRenderOptions
) {
  const { queryClient, router, ...renderOptions} = options || {};

  return render(ui, {
    wrapper: ({ children }) => (
      <AllProviders queryClient={queryClient} router={router}>
        {children}
      </AllProviders>
    ),
    ...renderOptions,
  });
}

// ============================================================================
// Custom Matchers / Assertions
// ============================================================================

/**
 * Wartet bis ein Element mit bestimmtem Text erscheint
 */
export async function waitForTextToAppear(
  getByText: (text: string | RegExp) => HTMLElement,
  text: string | RegExp,
  timeout = 1000
): Promise<HTMLElement> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      try {
        const element = getByText(text);
        clearInterval(interval);
        resolve(element);
      } catch {
        if (Date.now() - startTime > timeout) {
          clearInterval(interval);
          reject(new Error(`Text "${text}" did not appear within ${timeout}ms`));
        }
      }
    }, 50);
  });
}

// ============================================================================
// Mock Data Factories
// ============================================================================

/**
 * Erstellt Mock-Dokumentdaten
 */
export function createMockDocument(overrides = {}) {
  return {
    id: 'doc-123',
    filename: 'test-dokument.pdf',
    category: 'Rechnung',
    status: 'processed',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Erstellt Mock-Entity-Daten
 */
export function createMockEntity(overrides = {}) {
  return {
    id: 'entity-123',
    name: 'Test GmbH',
    entity_type: 'customer',
    risk_score: 35,
    ...overrides,
  };
}

/**
 * Erstellt Mock-Activity-Event
 */
export function createMockActivityEvent(overrides = {}) {
  return {
    event_id: 'event-123',
    event_type: 'document.uploaded',
    timestamp: new Date().toISOString(),
    priority: 'normal',
    payload: {
      filename: 'test.pdf',
      document_id: 'doc-123',
    },
    ...overrides,
  };
}

// ============================================================================
// Re-exports
// ============================================================================

export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';
