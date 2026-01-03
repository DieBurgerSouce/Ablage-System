/**
 * Dashboard Feature Module
 *
 * Exports alle Dashboard-relevanten Komponenten, Hooks und APIs.
 */

// API
export * from './api';

// Hooks
export {
  useDefaultDashboard,
  useDashboardList,
  useDashboard,
  useAvailableWidgets,
  useTemplates,
  useCreateDashboard,
  useUpdateDashboard,
  useDeleteDashboard,
  useUpdateLayout,
  useAddWidget,
  useUpdateWidget,
  useRemoveWidget,
  useApplyTemplate,
} from './hooks/useDashboard';

export {
  useWidgetPermissions,
  useCanViewWidget,
  type PermissionFilteredWidget,
} from './hooks/useWidgetPermissions';

// Registry
export {
  widgetRegistry,
  WIDGET_REGISTRY,
  normalizeWidgetType,
  getWidgetComponent,
  getWidgetLabel,
  getWidgetDefinition,
  getAllWidgets,
  getWidgetsByCategory,
  type WidgetRegistryEntry,
} from './registry';

// Store
export { useDashboardStore, type WidgetItem } from './stores/useDashboardStore';

// Components
export { DashboardGrid } from './components/DashboardGrid';
export { SortableWidget } from './components/SortableWidget';
export { WidgetCatalogDrawer } from './components/WidgetCatalogDrawer';
export { WidgetPreviewCard } from './components/WidgetPreviewCard';
