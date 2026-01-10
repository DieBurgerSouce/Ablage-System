/**
 * Dashboard React Query Hooks
 *
 * React Query Hooks fuer Dashboard-Management mit optimistic updates.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getDefaultDashboard,
  listDashboards,
  getDashboard,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  updateLayout,
  addWidget,
  updateWidget,
  removeWidget,
  getAvailableWidgets,
  getTemplates,
  applyTemplate,
  dashboardKeys,
  type Dashboard,
  type DashboardCreate,
  type DashboardUpdate,
  type WidgetCreate,
  type WidgetUpdate,
  type LayoutUpdatePayload,
} from '../api';

// =============================================================================
// Dashboard Queries
// =============================================================================

/**
 * Hook to fetch the user's default dashboard.
 */
export function useDefaultDashboard() {
  return useQuery({
    queryKey: dashboardKeys.default(),
    queryFn: getDefaultDashboard,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

/**
 * Hook to list all user dashboards.
 */
export function useDashboardList() {
  return useQuery({
    queryKey: dashboardKeys.list(),
    queryFn: listDashboards,
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook to fetch a specific dashboard.
 */
export function useDashboard(dashboardId: string | undefined) {
  return useQuery({
    queryKey: dashboardKeys.detail(dashboardId ?? ''),
    queryFn: () => getDashboard(dashboardId!),
    enabled: !!dashboardId,
    staleTime: 1000 * 60 * 5,
  });
}

/**
 * Hook to get available widgets based on permissions.
 */
export function useAvailableWidgets() {
  return useQuery({
    queryKey: dashboardKeys.availableWidgets(),
    queryFn: getAvailableWidgets,
    staleTime: 1000 * 60 * 30, // 30 minutes (permissions don't change often)
  });
}

/**
 * Hook to get dashboard templates.
 */
export function useTemplates(category?: string) {
  return useQuery({
    queryKey: dashboardKeys.templates(category),
    queryFn: () => getTemplates(category),
    staleTime: 1000 * 60 * 30,
  });
}

// =============================================================================
// Dashboard Mutations
// =============================================================================

/**
 * Hook to create a new dashboard.
 */
export function useCreateDashboard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: DashboardCreate) => createDashboard(data),
    onSuccess: (dashboard) => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.list() });
      if (dashboard.is_default) {
        queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
      }
      toast.success('Dashboard erstellt');
    },
    onError: () => {
      toast.error('Dashboard konnte nicht erstellt werden');
    },
  });
}

/**
 * Hook to update a dashboard.
 */
export function useUpdateDashboard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      dashboardId,
      data,
    }: {
      dashboardId: string;
      data: DashboardUpdate;
    }) => updateDashboard(dashboardId, data),
    onSuccess: (dashboard) => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.list() });
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.detail(dashboard.id),
      });
      if (dashboard.is_default) {
        queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
      }
      toast.success('Dashboard aktualisiert');
    },
    onError: () => {
      toast.error('Dashboard konnte nicht aktualisiert werden');
    },
  });
}

/**
 * Hook to delete a dashboard.
 */
export function useDeleteDashboard() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (dashboardId: string) => deleteDashboard(dashboardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.list() });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
      toast.success('Dashboard gelöscht');
    },
    onError: () => {
      toast.error(
        'Dashboard konnte nicht gelöscht werden. Mindestens ein Dashboard muss existieren.'
      );
    },
  });
}

// =============================================================================
// Layout Mutations
// =============================================================================

/**
 * Hook to update dashboard layout with optimistic updates.
 */
export function useUpdateLayout(dashboardId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: LayoutUpdatePayload) =>
      updateLayout(dashboardId, payload),
    onMutate: async (payload) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: dashboardKeys.detail(dashboardId),
      });

      // Snapshot previous value
      const previousDashboard = queryClient.getQueryData<Dashboard>(
        dashboardKeys.detail(dashboardId)
      );

      // Optimistically update
      if (previousDashboard) {
        const updatedWidgets = previousDashboard.widgets.map((widget) => {
          const update = payload.widgets.find((w) => w.id === widget.id);
          if (update) {
            return {
              ...widget,
              x: update.x,
              y: update.y,
              w: update.w,
              h: update.h,
            };
          }
          return widget;
        });

        queryClient.setQueryData(dashboardKeys.detail(dashboardId), {
          ...previousDashboard,
          widgets: updatedWidgets,
        });
      }

      return { previousDashboard };
    },
    onError: (_err, _payload, context) => {
      // Rollback on error
      if (context?.previousDashboard) {
        queryClient.setQueryData(
          dashboardKeys.detail(dashboardId),
          context.previousDashboard
        );
      }
      toast.error('Layout konnte nicht gespeichert werden');
    },
    onSettled: () => {
      // Refetch after mutation
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.detail(dashboardId),
      });
    },
  });
}

// =============================================================================
// Widget Mutations
// =============================================================================

/**
 * Hook to add a widget to a dashboard.
 */
export function useAddWidget(dashboardId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: WidgetCreate) => addWidget(dashboardId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.detail(dashboardId),
      });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
      toast.success('Widget hinzugefügt');
    },
    onError: () => {
      toast.error('Widget konnte nicht hinzugefügt werden');
    },
  });
}

/**
 * Hook to update a widget.
 */
export function useUpdateWidget(dashboardId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      widgetId,
      data,
    }: {
      widgetId: string;
      data: WidgetUpdate;
    }) => updateWidget(dashboardId, widgetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: dashboardKeys.detail(dashboardId),
      });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
    },
    onError: () => {
      toast.error('Widget konnte nicht aktualisiert werden');
    },
  });
}

/**
 * Hook to remove a widget from a dashboard.
 */
export function useRemoveWidget(dashboardId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (widgetId: string) => removeWidget(dashboardId, widgetId),
    onMutate: async (widgetId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: dashboardKeys.detail(dashboardId),
      });

      // Snapshot
      const previousDashboard = queryClient.getQueryData<Dashboard>(
        dashboardKeys.detail(dashboardId)
      );

      // Optimistic remove
      if (previousDashboard) {
        queryClient.setQueryData(dashboardKeys.detail(dashboardId), {
          ...previousDashboard,
          widgets: previousDashboard.widgets.filter((w) => w.id !== widgetId),
        });
      }

      return { previousDashboard };
    },
    onError: (_err, _widgetId, context) => {
      if (context?.previousDashboard) {
        queryClient.setQueryData(
          dashboardKeys.detail(dashboardId),
          context.previousDashboard
        );
      }
      toast.error('Widget konnte nicht entfernt werden');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.default() });
      toast.success('Widget entfernt');
    },
  });
}

// =============================================================================
// Template Mutations
// =============================================================================

/**
 * Hook to apply a template.
 */
export function useApplyTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, name }: { templateId: string; name?: string }) =>
      applyTemplate(templateId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: dashboardKeys.list() });
      toast.success('Dashboard aus Vorlage erstellt');
    },
    onError: () => {
      toast.error('Vorlage konnte nicht angewendet werden');
    },
  });
}
