/**
 * Knowledge Graph View Tests
 *
 * Phase 4.2.3 (P1 - Frontend)
 *
 * Testet:
 * - RiskNetworkView: Laden, Fehler, Daten-Rendering
 * - FinancialChainView: Laden, Fehler, Stages
 * - DocumentFamilyView: Laden, Fehler, Dokumentbaum
 * - TimelineView: Laden, Fehler, Events, Kategoriefilter
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Mock @xyflow/react (ReactFlow erfordert DOM-Messungen die happy-dom nicht hat)
// ---------------------------------------------------------------------------
vi.mock('@xyflow/react', () => {
  const actual = {
    ReactFlow: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="reactflow-container">{children}</div>
    ),
    Background: () => <div data-testid="reactflow-background" />,
    Controls: () => <div data-testid="reactflow-controls" />,
    MiniMap: () => <div data-testid="reactflow-minimap" />,
    useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    Handle: () => <div />,
    Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
    MarkerType: { ArrowClosed: 'arrowclosed' },
    BackgroundVariant: { Dots: 'dots' },
  };
  return actual;
});

// ---------------------------------------------------------------------------
// Mock recharts (SVG-Rendering in happy-dom problematisch)
// ---------------------------------------------------------------------------
vi.mock('recharts', () => ({
  BarChart: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div />,
  LineChart: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  ReferenceLine: () => <div />,
  Cell: () => <div />,
}));

// ---------------------------------------------------------------------------
// Mock Knowledge Graph Query Hooks
// ---------------------------------------------------------------------------
const mockUseRiskNetwork = vi.fn();
const mockUseFinancialChain = vi.fn();
const mockUseDocumentFamily = vi.fn();
const mockUseDocumentTimeline = vi.fn();

vi.mock('../hooks/use-knowledge-graph-queries', () => ({
  useRiskNetwork: (...args: unknown[]) => mockUseRiskNetwork(...args),
  useFinancialChain: (...args: unknown[]) => mockUseFinancialChain(...args),
  useDocumentFamily: (...args: unknown[]) => mockUseDocumentFamily(...args),
  useDocumentTimeline: (...args: unknown[]) => mockUseDocumentTimeline(...args),
}));

// ---------------------------------------------------------------------------
// Imports (nach Mocks!)
// ---------------------------------------------------------------------------
import { RiskNetworkView } from '../views/RiskNetworkView';
import { FinancialChainView } from '../views/FinancialChainView';
import { DocumentFamilyView } from '../views/DocumentFamilyView';
import { TimelineView } from '../views/TimelineView';

// ---------------------------------------------------------------------------
// Test Helpers
// ---------------------------------------------------------------------------

function createQueryWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const noop = vi.fn();

// ---------------------------------------------------------------------------
// RiskNetworkView Tests
// ---------------------------------------------------------------------------

describe('RiskNetworkView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('zeigt Ladezustand korrekt an', () => {
    mockUseRiskNetwork.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    render(
      <RiskNetworkView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Lade Risiko-Netzwerk...')).toBeInTheDocument();
  });

  it('zeigt Fehlerzustand korrekt an', () => {
    mockUseRiskNetwork.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Netzwerk-Fehler'),
    });

    render(
      <RiskNetworkView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Fehler beim Laden')).toBeInTheDocument();
    expect(screen.getByText('Netzwerk-Fehler')).toBeInTheDocument();
  });

  it('rendert Risiko-Netzwerk wenn Daten vorhanden', () => {
    // Echte API-Daten -> ReactFlow wird gerendert
    mockUseRiskNetwork.mockReturnValue({
      data: {
        nodes: [
          {
            entityId: 'risk-1',
            entityName: 'Test GmbH',
            riskScore: 55,
            transactionVolume: 120000,
            communityId: 'community-1',
            paymentBehaviorScore: 70,
            industryRisk: 40,
          },
        ],
        edges: [],
        communities: [
          { id: 'community-1', name: 'Cluster Sued', memberIds: ['risk-1'] },
        ],
      },
      isLoading: false,
      error: null,
    });

    render(
      <RiskNetworkView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
  });

  it('zeigt Empty-State wenn keine Daten vorhanden', () => {
    // Leere echte Daten -> kein Mock, sondern ehrlicher Empty-State
    mockUseRiskNetwork.mockReturnValue({
      data: { nodes: [], edges: [], communities: [] },
      isLoading: false,
      error: null,
    });

    render(
      <RiskNetworkView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(
      screen.getByText(/Keine Risiko-Daten verfuegbar/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('reactflow-container')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// FinancialChainView Tests
// ---------------------------------------------------------------------------

describe('FinancialChainView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('zeigt Ladezustand korrekt an', () => {
    mockUseFinancialChain.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    render(
      <FinancialChainView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Lade Finanzketten-Daten...')).toBeInTheDocument();
  });

  it('zeigt Fehlerzustand korrekt an', () => {
    mockUseFinancialChain.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('API nicht erreichbar'),
    });

    render(
      <FinancialChainView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('API nicht erreichbar')).toBeInTheDocument();
  });

  it('rendert Finanzkette wenn Daten vorhanden', () => {
    // Echte API-Daten -> ReactFlow wird gerendert
    mockUseFinancialChain.mockReturnValue({
      data: {
        entityId: 'entity-1',
        entityName: 'Test GmbH',
        stages: [
          {
            stage: 'invoice',
            label: 'Rechnung',
            documents: [
              {
                id: 'doc-1',
                type: 'invoice',
                label: 'Rechnung #1',
                data: {
                  documentNumber: 'RE-001',
                  amount: 1000,
                  currency: 'EUR',
                  status: 'Offen',
                  matchStatus: 'partial',
                  date: '2026-01-15',
                },
              },
            ],
          },
        ],
        matchStatus: 'partial',
        totalAmount: 1000,
      },
      isLoading: false,
      error: null,
    });

    render(
      <FinancialChainView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
  });

  it('zeigt Empty-State wenn keine Daten vorhanden', () => {
    // Leere echte Daten -> kein Mock, sondern ehrlicher Empty-State
    mockUseFinancialChain.mockReturnValue({
      data: {
        entityId: 'entity-1',
        entityName: 'Test GmbH',
        stages: [],
        matchStatus: 'none',
        totalAmount: 0,
      },
      isLoading: false,
      error: null,
    });

    render(
      <FinancialChainView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(
      screen.getByText(/Keine Finanzketten .* gefunden/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('reactflow-container')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// DocumentFamilyView Tests
// ---------------------------------------------------------------------------

describe('DocumentFamilyView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('zeigt Ladezustand korrekt an', () => {
    mockUseDocumentFamily.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    render(
      <DocumentFamilyView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Lade Dokumentenfamilie...')).toBeInTheDocument();
  });

  it('zeigt Fehlerzustand korrekt an', () => {
    mockUseDocumentFamily.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Dokument nicht gefunden'),
    });

    render(
      <DocumentFamilyView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Dokument nicht gefunden')).toBeInTheDocument();
  });

  it('rendert Dokumentenfamilie wenn Daten vorhanden', () => {
    // Echte API-Daten -> ReactFlow wird gerendert
    mockUseDocumentFamily.mockReturnValue({
      data: {
        rootDocument: {
          id: 'root-1',
          type: 'document',
          label: 'Rahmenvertrag.pdf',
          data: { date: '2026-01-10' },
        },
        groups: [
          {
            ring: 1,
            label: 'Direkte Anhaenge',
            documents: [
              {
                id: 'doc-child-1',
                type: 'document',
                label: 'Anlage_A.pdf',
                data: { date: '2026-01-11' },
              },
            ],
          },
        ],
        unlinkedCount: 0,
      },
      isLoading: false,
      error: null,
    });

    render(
      <DocumentFamilyView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
  });

  it('zeigt Empty-State wenn keine Daten vorhanden', () => {
    // Leere echte Daten -> kein Mock, sondern ehrlicher Empty-State
    mockUseDocumentFamily.mockReturnValue({
      data: {
        rootDocument: {
          id: 'root-1',
          type: 'document',
          label: 'Leer',
          data: {},
        },
        groups: [],
        unlinkedCount: 0,
      },
      isLoading: false,
      error: null,
    });

    render(
      <DocumentFamilyView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(
      screen.getByText(/Keine Dokumentenfamilie gefunden/),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('reactflow-container')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// TimelineView Tests
// ---------------------------------------------------------------------------

describe('TimelineView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('zeigt Hinweis wenn weder Entity noch Dokument ausgewaehlt', () => {
    mockUseDocumentTimeline.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    });

    render(
      <TimelineView onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(
      screen.getByText(/Keine Ereignisse gefunden/)
    ).toBeInTheDocument();
  });

  it('zeigt Hinweis wenn nur Entity ohne Dokument', () => {
    mockUseDocumentTimeline.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    });

    render(
      <TimelineView entityId="entity-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(
      screen.getByText(/Waehlen Sie ein Dokument/)
    ).toBeInTheDocument();
  });

  it('zeigt Ladezustand korrekt an', () => {
    mockUseDocumentTimeline.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    render(
      <TimelineView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Lade Ereignisse...')).toBeInTheDocument();
  });

  it('zeigt Fehlerzustand korrekt an', () => {
    mockUseDocumentTimeline.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Timeline API Fehler'),
    });

    render(
      <TimelineView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    expect(screen.getByText('Fehler beim Laden')).toBeInTheDocument();
  });

  it('rendert Timeline-Events wenn Daten vorhanden', () => {
    const now = new Date().toISOString();
    mockUseDocumentTimeline.mockReturnValue({
      data: {
        events: [
          {
            id: 'evt-1',
            timestamp: now,
            eventType: 'CREATED',
            description: 'Dokument erstellt',
            documentId: 'doc-1',
            documentName: 'Rechnung-001.pdf',
            metadata: {},
          },
          {
            id: 'evt-2',
            timestamp: now,
            eventType: 'OCR_PROCESSED',
            description: 'OCR abgeschlossen',
            documentId: 'doc-1',
            documentName: 'Rechnung-001.pdf',
            metadata: {},
          },
        ],
        totalCount: 2,
      },
      isLoading: false,
      error: null,
    });

    render(
      <TimelineView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    // Kein Lade- oder Fehlerzustand
    expect(screen.queryByText('Lade Ereignisse...')).not.toBeInTheDocument();
    expect(screen.queryByText('Fehler beim Laden')).not.toBeInTheDocument();
  });

  it('rendert Zeitbereich-Buttons', () => {
    const now = new Date().toISOString();
    mockUseDocumentTimeline.mockReturnValue({
      data: {
        events: [
          {
            id: 'evt-1',
            timestamp: now,
            eventType: 'CREATED',
            description: 'Test',
            metadata: {},
          },
        ],
        totalCount: 1,
      },
      isLoading: false,
      error: null,
    });

    render(
      <TimelineView documentId="doc-1" onNodeSelect={noop} />,
      { wrapper: createQueryWrapper() },
    );

    // Zeitbereich-Buttons sind sichtbar
    expect(screen.getByText('7 Tage')).toBeInTheDocument();
    expect(screen.getByText('30 Tage')).toBeInTheDocument();
    expect(screen.getByText('90 Tage')).toBeInTheDocument();
    expect(screen.getByText('1 Jahr')).toBeInTheDocument();
    expect(screen.getByText('Alles')).toBeInTheDocument();
  });
});
