/**
 * Widget Configuration Hook
 *
 * Provides server-side persistence for dashboard widget configuration.
 * Syncs local Zustand store with backend API.
 *
 * Features:
 * - Auto-sync on changes (debounced)
 * - Initial load from server
 * - Conflict resolution (server wins on load)
 * - Per-widget settings
 */

import { useCallback, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { logger } from '@/lib/logger';
import { useDashboardStore, type WidgetItem } from '../stores/useDashboardStore';

// ==================== Types ====================

export interface WidgetSettings {
  timeRange?: '7d' | '30d' | '90d' | '1y';
  filterTags?: string[];
  showLegend?: boolean;
  chartType?: 'line' | 'bar' | 'pie';
  maxItems?: number;
}

export interface WidgetConfigResponse {
  widgets: WidgetItem[];
  activePreset: string | null;
  compactMode: boolean;
  widgetSettings: Record<string, WidgetSettings>;
  lastSynced: string | null;
}

interface UpdateWidgetConfigRequest {
  widgets?: WidgetItem[];
  activePreset?: string | null;
  compactMode?: boolean;
  widgetSettings?: Record<string, WidgetSettings>;
}

// ==================== API Functions ====================

const widgetConfigKeys = {
  all: ['widget-config'] as const,
  config: () => [...widgetConfigKeys.all, 'config'] as const,
};

async function fetchWidgetConfig(): Promise<WidgetConfigResponse> {
  const response = await api.get('/settings/widget-config');
  // Convert snake_case to camelCase
  return {
    widgets: response.data.widgets,
    activePreset: response.data.active_preset,
    compactMode: response.data.compact_mode,
    widgetSettings: response.data.widget_settings || {},
    lastSynced: response.data.last_synced,
  };
}

async function updateWidgetConfig(
  data: UpdateWidgetConfigRequest
): Promise<WidgetConfigResponse> {
  // Convert camelCase to snake_case for API
  const payload: Record<string, unknown> = {};
  if (data.widgets !== undefined) payload.widgets = data.widgets;
  if (data.activePreset !== undefined) payload.active_preset = data.activePreset;
  if (data.compactMode !== undefined) payload.compact_mode = data.compactMode;
  if (data.widgetSettings !== undefined) {
    // Convert individual settings to snake_case
    const converted: Record<string, Record<string, unknown>> = {};
    for (const [widgetId, settings] of Object.entries(data.widgetSettings)) {
      converted[widgetId] = {
        time_range: settings.timeRange,
        filter_tags: settings.filterTags,
        show_legend: settings.showLegend,
        chart_type: settings.chartType,
        max_items: settings.maxItems,
      };
    }
    payload.widget_settings = converted;
  }

  const response = await api.put('/settings/widget-config', payload);
  return {
    widgets: response.data.widgets,
    activePreset: response.data.active_preset,
    compactMode: response.data.compact_mode,
    widgetSettings: response.data.widget_settings || {},
    lastSynced: response.data.last_synced,
  };
}

async function updateSingleWidgetSettings(
  widgetId: string,
  settings: WidgetSettings
): Promise<WidgetSettings> {
  const payload = {
    time_range: settings.timeRange,
    filter_tags: settings.filterTags,
    show_legend: settings.showLegend,
    chart_type: settings.chartType,
    max_items: settings.maxItems,
  };

  const response = await api.patch(
    `/settings/widget-config/widget/${encodeURIComponent(widgetId)}`,
    payload
  );

  return {
    timeRange: response.data.time_range,
    filterTags: response.data.filter_tags,
    showLegend: response.data.show_legend,
    chartType: response.data.chart_type,
    maxItems: response.data.max_items,
  };
}

async function resetWidgetConfig(): Promise<void> {
  await api.post('/settings/widget-config/reset');
}

// ==================== Hook ====================

interface UseWidgetConfigOptions {
  /** Enable auto-sync on store changes (default: true) */
  autoSync?: boolean;
  /** Debounce delay in ms for auto-sync (default: 1000) */
  debounceMs?: number;
  /** Load server config on mount (default: true) */
  loadOnMount?: boolean;
}

export function useWidgetConfig(options: UseWidgetConfigOptions = {}) {
  const { autoSync = true, debounceMs = 1000, loadOnMount = true } = options;

  const queryClient = useQueryClient();
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isInitialLoadRef = useRef(true);

  // Get store state and actions
  const widgets = useDashboardStore((state) => state.widgets);
  const activePreset = useDashboardStore((state) => state.activePreset);
  const compactMode = useDashboardStore((state) => state.compactMode);
  const setWidgets = useDashboardStore((state) => state.setWidgets);
  const setCompactMode = useDashboardStore((state) => state.setCompactMode);
  const applyPreset = useDashboardStore((state) => state.applyPreset);

  // Fetch config from server
  const {
    data: serverConfig,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: widgetConfigKeys.config(),
    queryFn: fetchWidgetConfig,
    enabled: loadOnMount,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });

  // Sync mutation
  const syncMutation = useMutation({
    mutationFn: updateWidgetConfig,
    onSuccess: (data) => {
      queryClient.setQueryData(widgetConfigKeys.config(), data);
    },
    onError: (error) => {
      logger.error('[WidgetConfig] Sync fehlgeschlagen:', error);
    },
  });

  // Single widget settings mutation
  const widgetSettingsMutation = useMutation({
    mutationFn: ({
      widgetId,
      settings,
    }: {
      widgetId: string;
      settings: WidgetSettings;
    }) => updateSingleWidgetSettings(widgetId, settings),
    onSuccess: (data, variables) => {
      // Update query cache
      queryClient.setQueryData(
        widgetConfigKeys.config(),
        (old: WidgetConfigResponse | undefined) => {
          if (!old) return old;
          return {
            ...old,
            widgetSettings: {
              ...old.widgetSettings,
              [variables.widgetId]: data,
            },
          };
        }
      );
    },
  });

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: resetWidgetConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: widgetConfigKeys.config() });
    },
  });

  // Apply server config to local store on initial load
  useEffect(() => {
    if (serverConfig && isInitialLoadRef.current && loadOnMount) {
      isInitialLoadRef.current = false;

      // Only apply if server has newer data
      const localStorageKey = 'dashboard-storage';
      const localData = localStorage.getItem(localStorageKey);
      let shouldApplyServer = true;

      if (localData) {
        try {
          const parsed = JSON.parse(localData);
          // If local storage exists but server has a last_synced, prefer server
          // This ensures multi-device sync works correctly
          if (serverConfig.lastSynced) {
            shouldApplyServer = true;
          } else if (parsed.state?.widgets?.length > 0) {
            // Local has data, server doesn't have sync timestamp - keep local
            shouldApplyServer = false;
          }
        } catch {
          // If parse fails, use server config
          shouldApplyServer = true;
        }
      }

      if (shouldApplyServer && serverConfig.widgets.length > 0) {
        setWidgets(serverConfig.widgets);
        setCompactMode(serverConfig.compactMode);
        if (serverConfig.activePreset) {
          applyPreset(serverConfig.activePreset);
        }
      }
    }
  }, [serverConfig, loadOnMount, setWidgets, setCompactMode, applyPreset]);

  // Auto-sync on changes (debounced)
  useEffect(() => {
    if (!autoSync || isInitialLoadRef.current) return;

    // Clear previous timeout
    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }

    // Debounce sync
    syncTimeoutRef.current = setTimeout(() => {
      syncMutation.mutate({
        widgets,
        activePreset,
        compactMode,
      });
    }, debounceMs);

    return () => {
      if (syncTimeoutRef.current) {
        clearTimeout(syncTimeoutRef.current);
      }
    };
  }, [widgets, activePreset, compactMode, autoSync, debounceMs, syncMutation]);

  // Force sync now (without debounce)
  const syncNow = useCallback(() => {
    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }
    return syncMutation.mutateAsync({
      widgets,
      activePreset,
      compactMode,
    });
  }, [widgets, activePreset, compactMode, syncMutation]);

  // Update individual widget settings
  const updateWidgetSettings = useCallback(
    (widgetId: string, settings: WidgetSettings) => {
      return widgetSettingsMutation.mutateAsync({ widgetId, settings });
    },
    [widgetSettingsMutation]
  );

  // Get settings for a widget
  const getWidgetSettings = useCallback(
    (widgetId: string): WidgetSettings | undefined => {
      return serverConfig?.widgetSettings[widgetId];
    },
    [serverConfig]
  );

  // Reset to defaults
  const resetToDefaults = useCallback(async () => {
    await resetMutation.mutateAsync();
    // Refetch will update local store via the effect
    await refetch();
  }, [resetMutation, refetch]);

  return {
    // State
    isLoading,
    isSyncing: syncMutation.isPending,
    error,
    lastSynced: serverConfig?.lastSynced
      ? new Date(serverConfig.lastSynced)
      : null,
    widgetSettings: serverConfig?.widgetSettings || {},

    // Actions
    syncNow,
    updateWidgetSettings,
    getWidgetSettings,
    resetToDefaults,
    refetch,
  };
}
