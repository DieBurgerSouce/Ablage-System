/**
 * LineageFlowchart Component
 *
 * Interaktive Visualisierung der Dokumenten-Lineage mit React Flow.
 * Zeigt die vollständige Verarbeitungskette eines Dokuments.
 *
 * Features:
 * - Horizontales/Vertikales Layout
 * - Filterung nach Event-Typen und Zeitraum
 * - Klickbare Nodes mit Detail-Panel
 * - Zoom/Pan mit Minimap
 * - Export der Lineage-Daten
 */

import { useCallback, useMemo, useState, useEffect } from 'react';
import { logger } from '@/lib/logger';
import {
  ReactFlow,
  Background,
  MiniMap,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  type NodeMouseHandler,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, FileText } from 'lucide-react';
import { isWithinInterval, parseISO } from 'date-fns';

import { useLineageData } from './hooks/useLineageData';
import {
  LineageNode,
  type LineageNodeData,
} from './components/LineageNode';
import { LineageEdge, LineageEdgeMarkerDefs, type LineageEdgeData } from './components/LineageEdge';
import { LineageControls, type LineageFilters, type LayoutDirection } from './components/LineageControls';
import { EventDetailPanel } from './components/EventDetailPanel';
import type { TimelineEntry, LineageEventType, EventTypeLabels } from '@/lib/api/services/lineage';
import { lineageService } from '@/lib/api/services/lineage';

// =============================================================================
// Types
// =============================================================================

export interface LineageFlowchartProps {
  /** Dokument-ID für den Lineage-Abruf */
  documentId: string;
  /** Höhe des Containers (Standard: 600px) */
  height?: number | string;
  /** Breite des Containers (Standard: 100%) */
  width?: number | string;
  /** Initiales Layout */
  initialLayout?: LayoutDirection;
  /** Zeige Minimap */
  showMinimap?: boolean;
  /** Zeige Controls */
  showControls?: boolean;
  /** Callback bei Klick auf Entity */
  onNavigateToEntity?: (entityId: string) => void;
  /** Callback bei Klick auf Dokument */
  onNavigateToDocument?: (documentId: string) => void;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

// =============================================================================
// Node Types Registration
// =============================================================================

const nodeTypes: NodeTypes = {
  lineageNode: LineageNode,
};

const edgeTypes: EdgeTypes = {
  lineageEdge: LineageEdge,
};

// =============================================================================
// Layout Configuration
// =============================================================================

const LAYOUT_CONFIG = {
  horizontal: {
    nodeWidth: 240,
    nodeHeight: 150,
    horizontalGap: 100,
    verticalGap: 50,
  },
  vertical: {
    nodeWidth: 240,
    nodeHeight: 150,
    horizontalGap: 50,
    verticalGap: 100,
  },
};

// =============================================================================
// Helper Functions
// =============================================================================

function calculateLayout(
  events: TimelineEntry[],
  eventTypeLabels: EventTypeLabels | undefined,
  direction: LayoutDirection
): { nodes: Node<LineageNodeData>[]; edges: Edge<LineageEdgeData>[] } {
  const config = LAYOUT_CONFIG[direction];
  const nodes: Node<LineageNodeData>[] = [];
  const edges: Edge<LineageEdgeData>[] = [];

  // Gruppiere Events nach Datum für besseres Layout
  const eventsByDate = new Map<string, TimelineEntry[]>();
  events.forEach((event) => {
    const date = event.timestamp.split('T')[0];
    if (!eventsByDate.has(date)) {
      eventsByDate.set(date, []);
    }
    eventsByDate.get(date)!.push(event);
  });

  let currentX = 0;
  let currentY = 0;
  let maxRowHeight = 0;
  const eventsPerRow = direction === 'horizontal' ? 1 : 3;
  let eventIndex = 0;

  events.forEach((event, index) => {
    const label = eventTypeLabels?.[event.eventType] || event.eventType.replace(/_/g, ' ');

    // Position berechnen
    if (direction === 'horizontal') {
      currentX = index * (config.nodeWidth + config.horizontalGap);
      currentY = 0;
    } else {
      const row = Math.floor(eventIndex / eventsPerRow);
      const col = eventIndex % eventsPerRow;
      currentX = col * (config.nodeWidth + config.horizontalGap);
      currentY = row * (config.nodeHeight + config.verticalGap);
      eventIndex++;
    }

    nodes.push({
      id: event.id,
      type: 'lineageNode',
      position: { x: currentX, y: currentY },
      data: {
        ...event,
        label,
      },
    });

    // Kante zum vorherigen Event
    if (index > 0) {
      const prevEvent = events[index - 1];
      const prevTimestamp = parseISO(prevEvent.timestamp);
      const currentTimestamp = parseISO(event.timestamp);
      const timeDeltaMs = currentTimestamp.getTime() - prevTimestamp.getTime();

      // Edge-Typ basierend auf Event-Typ
      let edgeType: 'default' | 'success' | 'error' | 'warning' = 'default';
      if (event.eventType === 'ocr_complete' || event.eventType === 'approval') {
        edgeType = 'success';
      } else if (event.eventType === 'ocr_failed' || event.eventType === 'rejection') {
        edgeType = 'error';
      } else if (event.eventType === 'escalation') {
        edgeType = 'warning';
      }

      edges.push({
        id: `${prevEvent.id}-${event.id}`,
        source: prevEvent.id,
        target: event.id,
        type: 'lineageEdge',
        data: {
          timeDeltaMs,
          showTiming: timeDeltaMs > 1000, // Zeige nur bei > 1s
          edgeType,
        },
        animated: event.eventType.includes('processing') || event.eventType === 'ocr_start',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 15,
          height: 15,
        },
      });
    }
  });

  return { nodes, edges };
}

function filterEvents(
  events: TimelineEntry[],
  filters: LineageFilters
): TimelineEntry[] {
  return events.filter((event) => {
    // Event-Typ Filter
    if (filters.eventTypes.length > 0) {
      if (!filters.eventTypes.includes(event.eventType as LineageEventType)) {
        return false;
      }
    }

    // Datums-Filter
    if (filters.dateRange.from || filters.dateRange.to) {
      const eventDate = parseISO(event.timestamp);

      if (filters.dateRange.from && filters.dateRange.to) {
        if (
          !isWithinInterval(eventDate, {
            start: filters.dateRange.from,
            end: filters.dateRange.to,
          })
        ) {
          return false;
        }
      } else if (filters.dateRange.from && eventDate < filters.dateRange.from) {
        return false;
      } else if (filters.dateRange.to && eventDate > filters.dateRange.to) {
        return false;
      }
    }

    return true;
  });
}

// =============================================================================
// Inner Component (mit ReactFlow-Kontext)
// =============================================================================

interface LineageFlowchartInnerProps extends LineageFlowchartProps {
  timeline: TimelineEntry[];
  eventTypeLabels: EventTypeLabels | undefined;
}

function LineageFlowchartInner({
  documentId,
  timeline,
  eventTypeLabels,
  height = 600,
  width = '100%',
  initialLayout = 'horizontal',
  showMinimap = true,
  showControls = true,
  onNavigateToEntity,
  onNavigateToDocument,
  className,
}: LineageFlowchartInnerProps) {
  const { fitView } = useReactFlow();

  // State
  const [layout, setLayout] = useState<LayoutDirection>(initialLayout);
  const [filters, setFilters] = useState<LineageFilters>({
    eventTypes: [],
    dateRange: { from: undefined, to: undefined },
  });
  const [selectedEvent, setSelectedEvent] = useState<TimelineEntry | null>(null);
  const [detailPanelOpen, setDetailPanelOpen] = useState(false);

  // Gefilterte Events
  const filteredEvents = useMemo(
    () => filterEvents(timeline, filters),
    [timeline, filters]
  );

  // Layout berechnen
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => calculateLayout(filteredEvents, eventTypeLabels, layout),
    [filteredEvents, eventTypeLabels, layout]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update Nodes/Edges wenn sich die Berechnung ändert
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);

    // Fit view nach Änderung
    setTimeout(() => {
      fitView({ padding: 0.2, duration: 300 });
    }, 50);
  }, [initialNodes, initialEdges, setNodes, setEdges, fitView]);

  // Node Click Handler
  const handleNodeClick: NodeMouseHandler<Node<LineageNodeData>> = useCallback(
    (_, node) => {
      const event = timeline.find((e) => e.id === node.id);
      if (event) {
        setSelectedEvent(event);
        setDetailPanelOpen(true);
      }
    },
    [timeline]
  );

  // Export Handler
  const handleExport = useCallback(async () => {
    try {
      const blob = await lineageService.exportLineage(documentId, 'json');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `lineage_${documentId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      logger.error('Export fehlgeschlagen:', error);
    }
  }, [documentId]);

  // Layout Change Handler
  const handleLayoutChange = useCallback((newLayout: LayoutDirection) => {
    setLayout(newLayout);
  }, []);

  return (
    <div
      className={cn('relative rounded-lg border overflow-hidden', className)}
      style={{ height, width }}
    >
      {/* SVG Defs für Edge Markers */}
      <LineageEdgeMarkerDefs />

      {/* Controls */}
      {showControls && (
        <LineageControls
          eventTypeLabels={eventTypeLabels}
          filters={filters}
          onFiltersChange={setFilters}
          layout={layout}
          onLayoutChange={handleLayoutChange}
          onExport={handleExport}
          className="absolute top-0 left-0 right-0 z-10"
        />
      )}

      {/* React Flow */}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        defaultEdgeOptions={{
          type: 'lineageEdge',
        }}
        proOptions={{ hideAttribution: true }}
        className={cn(showControls && 'pt-12')}
      >
        <Background gap={20} size={1} />

        {/* Standard Controls (optional) */}
        {!showControls && <Controls position="bottom-right" />}

        {/* Minimap */}
        {showMinimap && (
          <MiniMap
            position="bottom-right"
            nodeStrokeWidth={2}
            nodeBorderRadius={8}
            maskColor="rgba(0, 0, 0, 0.1)"
            className="bg-background/95 border rounded-lg shadow-md"
            style={{ width: 150, height: 100 }}
          />
        )}
      </ReactFlow>

      {/* Empty State */}
      {filteredEvents.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/80">
          <div className="text-center space-y-2">
            <FileText className="h-12 w-12 text-muted-foreground mx-auto" />
            <p className="text-lg font-medium">Keine Events gefunden</p>
            <p className="text-sm text-muted-foreground">
              {filters.eventTypes.length > 0 || filters.dateRange.from
                ? 'Versuchen Sie, die Filter anzupassen.'
                : 'Für dieses Dokument sind noch keine Lineage-Events vorhanden.'}
            </p>
          </div>
        </div>
      )}

      {/* Detail Panel */}
      <EventDetailPanel
        event={selectedEvent}
        eventTypeLabels={eventTypeLabels}
        open={detailPanelOpen}
        onOpenChange={setDetailPanelOpen}
        onNavigateToDocument={onNavigateToDocument}
        onNavigateToEntity={onNavigateToEntity}
      />
    </div>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function LineageFlowchart(props: LineageFlowchartProps) {
  const {
    documentId,
    height = 600,
    width = '100%',
    className,
  } = props;

  // Daten laden
  const {
    timeline,
    eventTypeLabels,
    isLoading,
    isError,
    errors,
  } = useLineageData(documentId);

  // Loading State
  if (isLoading) {
    return (
      <div
        className={cn('relative rounded-lg border overflow-hidden', className)}
        style={{ height, width }}
      >
        <div className="p-4 space-y-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-24" />
            <Skeleton className="h-10 w-24" />
          </div>
          <div className="flex items-center justify-center h-[500px]">
            <div className="text-center space-y-4">
              <Skeleton className="h-20 w-48 mx-auto" />
              <Skeleton className="h-4 w-32 mx-auto" />
              <Skeleton className="h-4 w-40 mx-auto" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error State
  if (isError) {
    const errorMessage = errors.find((e) => e)?.message || 'Unbekannter Fehler';

    return (
      <div
        className={cn('relative rounded-lg border overflow-hidden p-6', className)}
        style={{ height, width }}
      >
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Fehler beim Laden der Lineage-Daten: {errorMessage}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  // No Data State
  if (!timeline || timeline.events.length === 0) {
    return (
      <div
        className={cn('relative rounded-lg border overflow-hidden', className)}
        style={{ height, width }}
      >
        <div className="flex items-center justify-center h-full">
          <div className="text-center space-y-2">
            <FileText className="h-12 w-12 text-muted-foreground mx-auto" />
            <p className="text-lg font-medium">Keine Lineage-Daten</p>
            <p className="text-sm text-muted-foreground">
              Für dieses Dokument sind noch keine Lineage-Events vorhanden.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <LineageFlowchartInner
        {...props}
        timeline={timeline.events}
        eventTypeLabels={eventTypeLabels}
      />
    </ReactFlowProvider>
  );
}

// =============================================================================
// Export
// =============================================================================

export default LineageFlowchart;
