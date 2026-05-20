/**
 * DocumentGraphView + DocumentTimelineView Tests
 *
 * Testet Graph-Rendering, Loading/Error/Empty States, und Timeline.
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DocumentGraphView } from '../components/DocumentGraphView';
import { DocumentTimelineView } from '../components/DocumentTimelineView';
import type { DocumentChain } from '../types/document-graph-types';
import type { TimelineEntry } from '@/lib/api/services/lineage';

// Mock @xyflow/react
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="reactflow-container">{children}</div>
  ),
  Background: () => <div data-testid="reactflow-background" />,
  Controls: () => <div data-testid="reactflow-controls" />,
  MiniMap: () => <div data-testid="reactflow-minimap" />,
  useNodesState: (initial: unknown[]) => [initial || [], vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown[]) => [initial || [], vi.fn(), vi.fn()],
  Handle: () => <div />,
  BaseEdge: () => <div />,
  EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  getSmoothStepPath: () => ['', 0, 0],
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
  BackgroundVariant: { Dots: 'dots' },
}));

// Mock @tanstack/react-router
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
}));

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

// ==================== Mock Data ====================

const mockChain: DocumentChain = {
  chainId: 'CHAIN-2026-00001',
  documentCount: 3,
  chainStartedAt: '2026-01-15T10:00:00Z',
  chainUpdatedAt: '2026-02-20T14:30:00Z',
  hasQuote: true,
  hasOrder: true,
  hasDeliveryNote: false,
  hasInvoice: true,
  hasCreditNote: false,
  openDiscrepancies: 0,
  isComplete: false,
  documents: [
    {
      id: 'doc-1',
      documentType: 'quote',
      chainPosition: 1,
      filename: 'Angebot-2026-001.pdf',
      documentDate: '2026-01-15',
      amount: 1500.0,
      referenceNumbers: null,
      createdAt: '2026-01-15T10:00:00Z',
    },
    {
      id: 'doc-2',
      documentType: 'order',
      chainPosition: 2,
      filename: 'Auftrag-2026-001.pdf',
      documentDate: '2026-01-20',
      amount: 1500.0,
      referenceNumbers: null,
      createdAt: '2026-01-20T09:00:00Z',
    },
    {
      id: 'doc-3',
      documentType: 'invoice',
      chainPosition: 3,
      filename: 'Rechnung-2026-001.pdf',
      documentDate: '2026-02-15',
      amount: 1500.0,
      referenceNumbers: null,
      createdAt: '2026-02-15T11:00:00Z',
    },
  ],
};

const mockTimelineEvents: TimelineEntry[] = [
  {
    id: 'evt-1',
    eventType: 'import',
    eventData: {},
    timestamp: '2026-01-15T10:00:00Z',
    durationMs: null,
    confidence: null,
    userId: 'user-1',
    sourceService: 'upload',
  },
  {
    id: 'evt-2',
    eventType: 'ocr_complete',
    eventData: {},
    timestamp: '2026-01-15T10:01:00Z',
    durationMs: 2500,
    confidence: 0.95,
    userId: null,
    sourceService: 'deepseek',
  },
  {
    id: 'evt-3',
    eventType: 'classification',
    eventData: {},
    timestamp: '2026-01-15T10:01:05Z',
    durationMs: 150,
    confidence: 0.88,
    userId: null,
    sourceService: 'classifier',
  },
];

// ==================== DocumentGraphView Tests ====================

describe('DocumentGraphView', () => {
  it('zeigt Loading-State', () => {
    renderWithProviders(
      <DocumentGraphView chains={[]} isLoading={true} error={null} />
    );
    expect(screen.getByText('Lade Dokumenten-Graph...')).toBeInTheDocument();
  });

  it('zeigt Error-State', () => {
    renderWithProviders(
      <DocumentGraphView
        chains={[]}
        isLoading={false}
        error={new Error('Netzwerkfehler')}
      />
    );
    expect(screen.getByText('Fehler beim Laden des Graphen')).toBeInTheDocument();
    expect(screen.getByText('Netzwerkfehler')).toBeInTheDocument();
  });

  it('zeigt Empty-State wenn keine Ketten', () => {
    renderWithProviders(
      <DocumentGraphView chains={[]} isLoading={false} error={null} />
    );
    expect(screen.getByText('Keine Auftragsketten gefunden')).toBeInTheDocument();
  });

  it('rendert ReactFlow bei vorhandenen Ketten', () => {
    renderWithProviders(
      <DocumentGraphView
        chains={[mockChain]}
        isLoading={false}
        error={null}
      />
    );
    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
  });
});

// ==================== DocumentTimelineView Tests ====================

describe('DocumentTimelineView', () => {
  it('zeigt Loading-Skeleton', () => {
    renderWithProviders(
      <DocumentTimelineView events={[]} isLoading={true} />
    );
    // Skeleton elements should be present
    expect(screen.getByText('Dokumenten-Timeline')).toBeInTheDocument();
  });

  it('zeigt Empty-State wenn keine Events', () => {
    renderWithProviders(
      <DocumentTimelineView events={[]} isLoading={false} />
    );
    expect(screen.getByText('Keine Ereignisse gefunden')).toBeInTheDocument();
  });

  it('zeigt Events chronologisch gruppiert', () => {
    renderWithProviders(
      <DocumentTimelineView
        events={mockTimelineEvents}
        isLoading={false}
        documentTitle="Test-Dokument"
      />
    );

    expect(screen.getByText('Importiert')).toBeInTheDocument();
    expect(screen.getByText('OCR abgeschlossen')).toBeInTheDocument();
    expect(screen.getByText('Klassifiziert')).toBeInTheDocument();
    expect(screen.getByText('3 Ereignisse')).toBeInTheDocument();
  });

  it('zeigt Konfidenz-Werte an', () => {
    renderWithProviders(
      <DocumentTimelineView
        events={mockTimelineEvents}
        isLoading={false}
      />
    );

    expect(screen.getByText('Konfidenz: 95%')).toBeInTheDocument();
    expect(screen.getByText('Konfidenz: 88%')).toBeInTheDocument();
  });

  it('zeigt Dauer-Badges an', () => {
    renderWithProviders(
      <DocumentTimelineView
        events={mockTimelineEvents}
        isLoading={false}
      />
    );

    expect(screen.getByText('2.5s')).toBeInTheDocument();
    expect(screen.getByText('150ms')).toBeInTheDocument();
  });

  it('zeigt Source-Service Badges an', () => {
    renderWithProviders(
      <DocumentTimelineView
        events={mockTimelineEvents}
        isLoading={false}
      />
    );

    expect(screen.getByText('upload')).toBeInTheDocument();
    expect(screen.getByText('deepseek')).toBeInTheDocument();
  });
});
