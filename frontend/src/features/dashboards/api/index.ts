/**
 * Dashboard API Client
 *
 * API-Integration für personalisierte Dashboards
 */

import type {
  Dashboard,
  CreateDashboardRequest,
  UpdateDashboardRequest,
  AddWidgetRequest,
  UpdateWidgetRequest,
  UpdateLayoutRequest,
  ShareDashboardRequest,
  ShareInfo,
  DashboardPreset,
  WidgetDefinition,
  SharedDashboard,
} from '../types';

const API_BASE = '/api/v1/dashboards';

// Dashboard CRUD
export async function getDashboards(): Promise<Dashboard[]> {
  const response = await fetch(API_BASE, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Laden der Dashboards');
  }
  return response.json();
}

export async function getSharedDashboards(): Promise<SharedDashboard[]> {
  const response = await fetch(`${API_BASE}/shared`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Laden der geteilten Dashboards');
  }
  return response.json();
}

export async function getDashboard(id: string): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${id}`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Dashboard nicht gefunden');
  }
  return response.json();
}

export async function createDashboard(
  data: CreateDashboardRequest
): Promise<Dashboard> {
  const response = await fetch(API_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Erstellen des Dashboards');
  }
  return response.json();
}

export async function updateDashboard(
  id: string,
  data: UpdateDashboardRequest
): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Aktualisieren des Dashboards');
  }
  return response.json();
}

export async function deleteDashboard(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Löschen des Dashboards');
  }
}

export async function duplicateDashboard(id: string): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${id}/duplicate`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Duplizieren des Dashboards');
  }
  return response.json();
}

// Favorites
export async function setFavorite(
  id: string,
  is_favorite: boolean
): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${id}/favorite`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ is_favorite }),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Setzen des Favoriten');
  }
  return response.json();
}

// Widgets
export async function getAvailableWidgets(): Promise<WidgetDefinition[]> {
  const response = await fetch(`${API_BASE}/widgets/available`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Laden der verfügbaren Widgets');
  }
  return response.json();
}

export async function addWidget(
  dashboardId: string,
  data: AddWidgetRequest
): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${dashboardId}/widgets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Hinzufügen des Widgets');
  }
  return response.json();
}

export async function updateWidget(
  dashboardId: string,
  widgetId: string,
  data: UpdateWidgetRequest
): Promise<Dashboard> {
  const response = await fetch(
    `${API_BASE}/${dashboardId}/widgets/${widgetId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    }
  );
  if (!response.ok) {
    throw new Error('Fehler beim Aktualisieren des Widgets');
  }
  return response.json();
}

export async function deleteWidget(
  dashboardId: string,
  widgetId: string
): Promise<Dashboard> {
  const response = await fetch(
    `${API_BASE}/${dashboardId}/widgets/${widgetId}`,
    {
      method: 'DELETE',
      credentials: 'include',
    }
  );
  if (!response.ok) {
    throw new Error('Fehler beim Löschen des Widgets');
  }
  return response.json();
}

export async function saveLayout(
  dashboardId: string,
  data: UpdateLayoutRequest
): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/${dashboardId}/layout`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Speichern des Layouts');
  }
  return response.json();
}

// Sharing
export async function shareDashboard(
  dashboardId: string,
  data: ShareDashboardRequest
): Promise<void> {
  const response = await fetch(`${API_BASE}/${dashboardId}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error('Fehler beim Teilen des Dashboards');
  }
}

export async function unshareDashboard(
  dashboardId: string,
  userId: string
): Promise<void> {
  const response = await fetch(`${API_BASE}/${dashboardId}/share/${userId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Entfernen der Berechtigung');
  }
}

export async function getShareInfo(dashboardId: string): Promise<ShareInfo[]> {
  const response = await fetch(`${API_BASE}/${dashboardId}/share`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Laden der Freigabe-Informationen');
  }
  return response.json();
}

// Presets
export async function getPresets(): Promise<DashboardPreset[]> {
  const response = await fetch(`${API_BASE}/presets`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Laden der Vorlagen');
  }
  return response.json();
}

export async function createFromPreset(presetId: string): Promise<Dashboard> {
  const response = await fetch(`${API_BASE}/presets/${presetId}/create`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Fehler beim Erstellen aus Vorlage');
  }
  return response.json();
}
