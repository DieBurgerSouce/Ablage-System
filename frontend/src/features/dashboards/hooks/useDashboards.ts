/**
 * Dashboard Hooks
 *
 * TanStack Query Hooks für Dashboard-Verwaltung
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query';
import * as api from '../api';
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

// Query Keys
export const dashboardKeys = {
  all: ['dashboards'] as const,
  lists: () => [...dashboardKeys.all, 'list'] as const,
  list: () => [...dashboardKeys.lists()] as const,
  shared: () => [...dashboardKeys.all, 'shared'] as const,
  detail: (id: string) => [...dashboardKeys.all, id] as const,
  shareInfo: (id: string) => [...dashboardKeys.all, id, 'share'] as const,
  presets: () => ['dashboard-presets'] as const,
  widgets: () => ['available-widgets'] as const,
};

// List Dashboards
export function useDashboards(): UseQueryResult<Dashboard[], Error> {
  return useQuery({
    queryKey: dashboardKeys.list(),
    queryFn: api.getDashboards,
  });
}

// List Shared Dashboards
export function useSharedDashboards(): UseQueryResult<
  SharedDashboard[],
  Error
> {
  return useQuery({
    queryKey: dashboardKeys.shared(),
    queryFn: api.getSharedDashboards,
  });
}

// Get Single Dashboard
export function useDashboard(
  id: string,
  enabled = true
): UseQueryResult<Dashboard, Error> {
  return useQuery({
    queryKey: dashboardKeys.detail(id),
    queryFn: () => api.getDashboard(id),
    enabled: enabled && !!id,
  });
}

// Create Dashboard
export function useCreateDashboard(): UseMutationResult<
  Dashboard,
  Error,
  CreateDashboardRequest
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createDashboard,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Update Dashboard
export function useUpdateDashboard(
  id: string
): UseMutationResult<Dashboard, Error, UpdateDashboardRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => api.updateDashboard(id, data),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(id), data);
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Delete Dashboard
export function useDeleteDashboard(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.deleteDashboard,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Duplicate Dashboard
export function useDuplicateDashboard(): UseMutationResult<
  Dashboard,
  Error,
  string
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.duplicateDashboard,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Set Favorite
export function useSetFavorite(
  id: string
): UseMutationResult<Dashboard, Error, boolean> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (is_favorite) => api.setFavorite(id, is_favorite),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(id), data);
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Available Widgets
export function useAvailableWidgets(): UseQueryResult<
  WidgetDefinition[],
  Error
> {
  return useQuery({
    queryKey: dashboardKeys.widgets(),
    queryFn: api.getAvailableWidgets,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Add Widget
export function useAddWidget(
  dashboardId: string
): UseMutationResult<Dashboard, Error, AddWidgetRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => api.addWidget(dashboardId, data),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(dashboardId), data);
    },
  });
}

// Update Widget
export function useUpdateWidget(
  dashboardId: string
): UseMutationResult<
  Dashboard,
  Error,
  { widgetId: string; data: UpdateWidgetRequest }
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ widgetId, data }) =>
      api.updateWidget(dashboardId, widgetId, data),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(dashboardId), data);
    },
  });
}

// Delete Widget
export function useDeleteWidget(
  dashboardId: string
): UseMutationResult<Dashboard, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (widgetId) => api.deleteWidget(dashboardId, widgetId),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(dashboardId), data);
    },
  });
}

// Save Layout
export function useSaveLayout(
  dashboardId: string
): UseMutationResult<Dashboard, Error, UpdateLayoutRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => api.saveLayout(dashboardId, data),
    onSuccess: (data) => {
      queryClient.setQueryData(dashboardKeys.detail(dashboardId), data);
    },
  });
}

// Share Dashboard
export function useShareDashboard(
  dashboardId: string
): UseMutationResult<void, Error, ShareDashboardRequest> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data) => api.shareDashboard(dashboardId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.shareInfo(dashboardId),
      });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Unshare Dashboard
export function useUnshareDashboard(
  dashboardId: string
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (userId) => api.unshareDashboard(dashboardId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.shareInfo(dashboardId),
      });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}

// Get Share Info
export function useShareInfo(
  dashboardId: string
): UseQueryResult<ShareInfo[], Error> {
  return useQuery({
    queryKey: dashboardKeys.shareInfo(dashboardId),
    queryFn: () => api.getShareInfo(dashboardId),
    enabled: !!dashboardId,
  });
}

// Presets
export function usePresets(): UseQueryResult<DashboardPreset[], Error> {
  return useQuery({
    queryKey: dashboardKeys.presets(),
    queryFn: api.getPresets,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

// Create from Preset
export function useCreateFromPreset(): UseMutationResult<
  Dashboard,
  Error,
  string
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.createFromPreset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.lists() });
    },
  });
}
