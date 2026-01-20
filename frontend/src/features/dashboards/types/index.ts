/**
 * Dashboard Feature Types
 *
 * Typdefinitionen für das personalisierte Dashboard-System
 */

export type WidgetType =
  | 'document_count'
  | 'invoice_summary'
  | 'ocr_quality'
  | 'entity_list'
  | 'cashflow_chart'
  | 'recent_documents'
  | 'risk_overview'
  | 'workflow_status'
  | 'custom_chart';

export type PermissionLevel = 'view' | 'edit';

export interface Widget {
  id: string;
  type: WidgetType;
  title: string;
  config: Record<string, any>;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Dashboard {
  id: string;
  name: string;
  description?: string;
  widgets: Widget[];
  is_favorite: boolean;
  is_shared: boolean;
  created_at: string;
  updated_at: string;
  owner_id: string;
  company_id: string;
}

export interface LayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  maxW?: number;
  minH?: number;
  maxH?: number;
  static?: boolean;
}

export interface DashboardPreset {
  id: string;
  name: string;
  description: string;
  role: string;
  widgets: Omit<Widget, 'id'>[];
}

export interface ShareInfo {
  user_id: string;
  user_email: string;
  permission: PermissionLevel;
  shared_at?: string;
}

export interface CreateDashboardRequest {
  name: string;
  description?: string;
  widgets?: Omit<Widget, 'id'>[];
}

export interface UpdateDashboardRequest {
  name?: string;
  description?: string;
}

export interface AddWidgetRequest {
  type: WidgetType;
  title: string;
  config?: Record<string, any>;
  x?: number;
  y?: number;
  w?: number;
  h?: number;
}

export interface UpdateWidgetRequest {
  title?: string;
  config?: Record<string, any>;
}

export interface UpdateLayoutRequest {
  widgets: Array<{
    id: string;
    x: number;
    y: number;
    w: number;
    h: number;
  }>;
}

export interface ShareDashboardRequest {
  user_id: string;
  permission: PermissionLevel;
}

export interface WidgetDefinition {
  type: WidgetType;
  name: string;
  description: string;
  category: 'documents' | 'finance' | 'workflows' | 'analytics';
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
  maxSize?: { w: number; h: number };
  icon: string;
}

export interface DashboardListResponse {
  dashboards: Dashboard[];
  total: number;
}

export interface SharedDashboard extends Dashboard {
  owner_email: string;
  permission: PermissionLevel;
}
