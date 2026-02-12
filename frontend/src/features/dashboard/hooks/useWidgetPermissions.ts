/**
 * Widget Permissions Hook
 *
 * Filtert verfügbare Widgets basierend auf Benutzerberechtigungen.
 */

import { useMemo } from 'react';
import { useAvailableWidgets } from './useDashboard';
import { widgetRegistry, type WidgetRegistryEntry } from '../registry';

export interface PermissionFilteredWidget extends WidgetRegistryEntry {
  requiresPermission: boolean;
  requiredPermissions?: string[];
  isAvailable: boolean;
}

/**
 * Hook that returns widgets filtered by user permissions.
 * Combines widget registry with backend permission check.
 */
export function useWidgetPermissions() {
  const { data: availableWidgets, isLoading, error } = useAvailableWidgets();

  const filteredWidgets = useMemo((): PermissionFilteredWidget[] => {
    if (!availableWidgets) {
      // Return all widgets as unavailable while loading
      return Object.entries(widgetRegistry).map(([type, entry]) => ({
        ...entry,
        requiresPermission: true,
        isAvailable: false,
      }));
    }

    // Create a map of available widget types
    const availableMap = new Map(
      availableWidgets.map((w) => [w.widget_type, w])
    );

    // Map registry entries with availability info
    return Object.entries(widgetRegistry).map(([type, entry]) => {
      const available = availableMap.get(type);
      return {
        ...entry,
        requiresPermission: available?.requires_permission ?? true,
        requiredPermissions: available?.required_permissions,
        isAvailable: !!available,
      };
    });
  }, [availableWidgets]);

  const availableWidgetTypes = useMemo(() => {
    return filteredWidgets.filter((w) => w.isAvailable).map((w) => w.type);
  }, [filteredWidgets]);

  const canAddWidget = (widgetType: string): boolean => {
    return availableWidgetTypes.includes(widgetType);
  };

  const getWidgetsByCategory = (
    category: 'info' | 'action' | 'data' | 'finance'
  ): PermissionFilteredWidget[] => {
    return filteredWidgets.filter(
      (w) => w.isAvailable && w.category === category
    );
  };

  return {
    widgets: filteredWidgets,
    availableWidgets: filteredWidgets.filter((w) => w.isAvailable),
    unavailableWidgets: filteredWidgets.filter((w) => !w.isAvailable),
    availableWidgetTypes,
    canAddWidget,
    getWidgetsByCategory,
    isLoading,
    error,
  };
}

/**
 * Hook to check if a specific widget can be viewed.
 */
export function useCanViewWidget(widgetType: string) {
  const { availableWidgetTypes, isLoading } = useWidgetPermissions();

  return {
    canView: availableWidgetTypes.includes(widgetType),
    isLoading,
  };
}
