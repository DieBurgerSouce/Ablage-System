/**
 * Dashboard Components Index
 *
 * Exportiert alle Dashboard-Komponenten.
 */

// Grid Components
export { DashboardGrid } from "./DashboardGrid"
export { DashboardGridEnhanced } from "./DashboardGridEnhanced"

// Widget Components
export { SortableWidget } from "./SortableWidget"
export { ResizableWidget } from "./ResizableWidget"
export {
  DraggableWidget,
  WidgetDragOverlay,
  type WidgetData,
  type DraggableWidgetProps,
  type WidgetDragOverlayProps,
} from "./DraggableWidget"

// Widget Management
export { WidgetCatalogDrawer } from "./WidgetCatalogDrawer"
export { WidgetConfigModal } from "./WidgetConfigModal"
export { WidgetPreviewCard } from "./WidgetPreviewCard"
export { WidgetSyncStatus } from "./WidgetSyncStatus"
export { WidgetExportButton } from "./WidgetExportButton"

// Activity & Presets
export { ActivityFeed, ActivityFeedWidget } from "./ActivityFeed"
export { PresetSelector } from "./PresetSelector"

// Shared
export * from "./shared"
