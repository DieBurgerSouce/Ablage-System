/**
 * Dashboard API Client
 *
 * API-Funktionen fuer Dashboard-Management, Widget-CRUD und Layout-Persistenz.
 */

import { apiClient as api } from '@/lib/api/client';

const BASE_URL = '/dashboard';

// =============================================================================
// Types
// =============================================================================

export interface WidgetPosition {
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
}

export interface Widget {
  id: string;
  widget_type: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
  config?: Record<string, unknown>;
  title_override?: string;
  filter_overrides?: Record<string, unknown>;
  is_visible: boolean;
  is_collapsed: boolean;
  sort_order: number;
}

export interface Dashboard {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  columns: number;
  row_height: number;
  compact_type?: 'vertical' | 'horizontal' | null;
  default_date_range?: string;
  default_company_id?: string;
  created_at?: string;
  updated_at?: string;
  widgets: Widget[];
}

export interface DashboardListItem {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  widget_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface DashboardCreate {
  name: string;
  description?: string;
  is_default?: boolean;
  columns?: number;
  row_height?: number;
  compact_type?: 'vertical' | 'horizontal' | null;
  widgets?: Partial<Widget>[];
}

export interface DashboardUpdate {
  name?: string;
  description?: string;
  is_default?: boolean;
  columns?: number;
  row_height?: number;
  compact_type?: string;
  default_date_range?: string;
  default_company_id?: string;
}

export interface WidgetCreate {
  widget_type: string;
  position?: WidgetPosition;
  config?: Record<string, unknown>;
  title_override?: string;
}

export interface WidgetUpdate {
  position?: Partial<WidgetPosition>;
  config?: Record<string, unknown>;
  title_override?: string;
  is_visible?: boolean;
  is_collapsed?: boolean;
}

export interface AvailableWidget {
  widget_type: string;
  requires_permission: boolean;
  required_permissions?: string[];
}

export interface DashboardTemplate {
  id: string;
  name: string;
  description?: string;
  category: string;
  for_roles?: string[];
  layout: Partial<Widget>[];
  preview_image_url?: string;
}

export interface LayoutUpdatePayload {
  widgets: Array<{
    id: string;
    x: number;
    y: number;
    w: number;
    h: number;
  }>;
}

// =============================================================================
// Dashboard CRUD
// =============================================================================

/**
 * Get the user's default dashboard.
 * Creates a default dashboard if none exists.
 */
export async function getDefaultDashboard(): Promise<Dashboard> {
  const response = await api.get<Dashboard>(BASE_URL);
  return response.data;
}

/**
 * List all user dashboards.
 */
export async function listDashboards(): Promise<DashboardListItem[]> {
  const response = await api.get<DashboardListItem[]>(`${BASE_URL}/list`);
  return response.data;
}

/**
 * Get a specific dashboard by ID.
 */
export async function getDashboard(dashboardId: string): Promise<Dashboard> {
  const response = await api.get<Dashboard>(`${BASE_URL}/${dashboardId}`);
  return response.data;
}

/**
 * Create a new dashboard.
 */
export async function createDashboard(data: DashboardCreate): Promise<Dashboard> {
  const response = await api.post<Dashboard>(BASE_URL, data);
  return response.data;
}

/**
 * Update dashboard settings.
 */
export async function updateDashboard(
  dashboardId: string,
  data: DashboardUpdate
): Promise<Dashboard> {
  const response = await api.put<Dashboard>(`${BASE_URL}/${dashboardId}`, data);
  return response.data;
}

/**
 * Delete a dashboard.
 */
export async function deleteDashboard(dashboardId: string): Promise<void> {
  await api.delete(`${BASE_URL}/${dashboardId}`);
}

// =============================================================================
// Layout Management
// =============================================================================

/**
 * Update the entire dashboard layout (batch widget positions).
 * Used for drag & drop operations.
 */
export async function updateLayout(
  dashboardId: string,
  payload: LayoutUpdatePayload
): Promise<{ success: boolean; message: string }> {
  const response = await api.put<{ success: boolean; message: string }>(
    `${BASE_URL}/${dashboardId}/layout`,
    payload
  );
  return response.data;
}

// =============================================================================
// Widget Management
// =============================================================================

/**
 * Get available widgets based on user permissions.
 */
export async function getAvailableWidgets(): Promise<AvailableWidget[]> {
  const response = await api.get<AvailableWidget[]>(`${BASE_URL}/widgets/available`);
  return response.data;
}

/**
 * Add a widget to a dashboard.
 */
export async function addWidget(
  dashboardId: string,
  data: WidgetCreate
): Promise<Widget> {
  const response = await api.post<Widget>(
    `${BASE_URL}/${dashboardId}/widgets`,
    data
  );
  return response.data;
}

/**
 * Update a widget.
 */
export async function updateWidget(
  dashboardId: string,
  widgetId: string,
  data: WidgetUpdate
): Promise<Widget> {
  const response = await api.put<Widget>(
    `${BASE_URL}/${dashboardId}/widgets/${widgetId}`,
    data
  );
  return response.data;
}

/**
 * Remove a widget from a dashboard.
 */
export async function removeWidget(
  dashboardId: string,
  widgetId: string
): Promise<void> {
  await api.delete(`${BASE_URL}/${dashboardId}/widgets/${widgetId}`);
}

// =============================================================================
// Templates
// =============================================================================

/**
 * Get available dashboard templates.
 */
export async function getTemplates(category?: string): Promise<DashboardTemplate[]> {
  const response = await api.get<DashboardTemplate[]>(`${BASE_URL}/templates`, {
    params: category ? { category } : undefined,
  });
  return response.data;
}

/**
 * Apply a template to create a new dashboard.
 */
export async function applyTemplate(
  templateId: string,
  name?: string
): Promise<Dashboard> {
  const response = await api.post<Dashboard>(
    `${BASE_URL}/templates/${templateId}/apply`,
    null,
    { params: name ? { name } : undefined }
  );
  return response.data;
}

// =============================================================================
// React Query Keys
// =============================================================================

export const dashboardKeys = {
  all: ['dashboard'] as const,
  list: () => [...dashboardKeys.all, 'list'] as const,
  detail: (id: string) => [...dashboardKeys.all, 'detail', id] as const,
  default: () => [...dashboardKeys.all, 'default'] as const,
  widgets: () => [...dashboardKeys.all, 'widgets'] as const,
  availableWidgets: () => [...dashboardKeys.widgets(), 'available'] as const,
  templates: (category?: string) =>
    [...dashboardKeys.all, 'templates', category] as const,
};
