/**
 * Lineage Feature Exports
 *
 * Document Lineage Timeline Visualisierung für Ablage-System.
 */

// Main Component
export { LineageFlowchart, default as LineageFlowchartDefault } from './LineageFlowchart';
export type { LineageFlowchartProps } from './LineageFlowchart';

// Page Component
export {
  DocumentLineagePage,
  DocumentLineagePageWrapper,
} from './pages/DocumentLineagePage';
export type { DocumentLineagePageProps } from './pages/DocumentLineagePage';

// Sub-Components
export { LineageNode } from './components/LineageNode';
export type { LineageNodeData } from './components/LineageNode';

export { LineageEdge, LineageEdgeMarkerDefs } from './components/LineageEdge';
export type { LineageEdgeData } from './components/LineageEdge';

export { LineageControls } from './components/LineageControls';
export type {
  LineageControlsProps,
  LineageFilters,
  LayoutDirection,
  DateRange,
} from './components/LineageControls';

export { EventDetailPanel } from './components/EventDetailPanel';
export type { EventDetailPanelProps } from './components/EventDetailPanel';

export { LineageStatsCards } from './components/LineageStatsCards';
export type { LineageStatsCardsProps } from './components/LineageStatsCards';

// Hooks
export {
  useLineageData,
  useLineageTimeline,
  useLineageStats,
  useLineageSummary,
  useEventTypes,
  useImportSourceTypes,
  lineageQueryKeys,
} from './hooks/useLineageData';
export type {
  UseTimelineOptions,
  UseLineageDataResult,
} from './hooks/useLineageData';
