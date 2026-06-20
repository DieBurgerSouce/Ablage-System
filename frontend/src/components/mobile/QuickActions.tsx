/**
 * QuickActions Component
 *
 * Mobile-optimized quick action widget for common tasks.
 *
 * Features:
 * - One-tap document upload
 * - Quick approval buttons
 * - Pending items count badges
 * - Recent documents shortcut
 * - Offline-aware status
 *
 * All user-facing text is in German.
 */

import * as React from 'react';
import { Camera, Upload, CheckCircle2, Clock, Search, Plus, AlertTriangle, RefreshCw, WifiOff, Loader2, type LucideIcon } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { usePWA } from '@/context/PWAContext';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface QuickActionsProps {
  /** Called when an action is triggered */
  onAction?: (actionId: string) => void;
  /** Custom className */
  className?: string;
  /** Show as compact row or grid */
  variant?: 'grid' | 'row' | 'minimal';
  /** Show pending counts (requires API) */
  showCounts?: boolean;
  /** Custom actions to display */
  actions?: QuickActionItem[];
}

export interface QuickActionItem {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Badge count (e.g., pending items) */
  count?: number;
  /** Action is highlighted/primary */
  primary?: boolean;
  /** Action requires online */
  requiresOnline?: boolean;
  /** Navigation URL */
  href?: string;
  /** Click handler */
  onClick?: () => void;
  /** Show loading state */
  loading?: boolean;
  /** Disabled state */
  disabled?: boolean;
}

interface QuickActionCounts {
  pendingApprovals: number;
  recentDocuments: number;
  pendingUploads: number;
  unreadAlerts: number;
}

// ============================================
// Default Actions
// ============================================

const DEFAULT_ACTIONS: QuickActionItem[] = [
  {
    id: 'scan',
    label: 'Scannen',
    icon: Camera,
    primary: true,
  },
  {
    id: 'upload',
    label: 'Hochladen',
    icon: Upload,
  },
  {
    id: 'approvals',
    label: 'Genehmigungen',
    icon: CheckCircle2,
    requiresOnline: true,
  },
  {
    id: 'recent',
    label: 'Zuletzt',
    icon: Clock,
  },
  {
    id: 'search',
    label: 'Suchen',
    icon: Search,
  },
  {
    id: 'alerts',
    label: 'Warnungen',
    icon: AlertTriangle,
    requiresOnline: true,
  },
];

// ============================================
// API Hook
// ============================================

function useQuickActionCounts(enabled: boolean) {
  return useQuery<QuickActionCounts>({
    queryKey: ['quick-action-counts'],
    queryFn: async () => {
      const response = await apiClient.get('/dashboard/quick-counts');
      return response.data;
    },
    enabled,
    staleTime: 30 * 1000, // 30 seconds
    refetchInterval: 60 * 1000, // 1 minute
    retry: 1,
  });
}

// ============================================
// Component
// ============================================

export function QuickActions({
  onAction,
  className,
  variant = 'grid',
  showCounts = true,
  actions = DEFAULT_ACTIONS,
}: QuickActionsProps) {
  const { isOnline } = usePWA();
  const { data: counts, isLoading: countsLoading, refetch } = useQuickActionCounts(
    showCounts && isOnline
  );

  /**
   * Get count for action
   */
  const getCount = React.useCallback(
    (actionId: string): number | undefined => {
      if (!counts) return undefined;

      switch (actionId) {
        case 'approvals':
          return counts.pendingApprovals;
        case 'recent':
          return counts.recentDocuments;
        case 'alerts':
          return counts.unreadAlerts;
        default:
          return undefined;
      }
    },
    [counts]
  );

  /**
   * Handle action click
   */
  const handleAction = React.useCallback(
    (action: QuickActionItem) => {
      if (action.disabled) return;
      if (action.requiresOnline && !isOnline) {
        logger.warn('[QuickActions] Aktion erfordert Online-Verbindung', {
          actionId: action.id,
        });
        return;
      }

      action.onClick?.();
      onAction?.(action.id);
    },
    [isOnline, onAction]
  );

  // Minimal variant - just icons in a row
  if (variant === 'minimal') {
    return (
      <div className={cn('flex items-center gap-1', className)}>
        {actions.slice(0, 5).map((action) => {
          const Icon = action.icon;
          const count = action.count ?? getCount(action.id);
          const isDisabled =
            action.disabled || (action.requiresOnline && !isOnline);

          return (
            <Button
              key={action.id}
              variant={action.primary ? 'default' : 'ghost'}
              size="icon"
              onClick={() => handleAction(action)}
              disabled={isDisabled}
              className={cn(
                'relative h-10 w-10',
                action.primary && 'bg-primary text-primary-foreground'
              )}
              title={action.label}
            >
              <Icon className="h-5 w-5" />
              {count !== undefined && count > 0 && (
                <Badge
                  variant="destructive"
                  className="absolute -top-1 -right-1 h-5 min-w-5 px-1 text-[10px]"
                >
                  {count > 99 ? '99+' : count}
                </Badge>
              )}
            </Button>
          );
        })}
      </div>
    );
  }

  // Row variant - horizontal scroll
  if (variant === 'row') {
    return (
      <div className={cn('w-full', className)}>
        {/* Offline indicator */}
        {!isOnline && (
          <div className="flex items-center gap-2 px-2 py-1 mb-2 text-sm text-yellow-600 bg-yellow-50 dark:bg-yellow-950/30 dark:text-yellow-400 rounded-lg">
            <WifiOff className="h-4 w-4" />
            <span>Offline - einige Funktionen eingeschraenkt</span>
          </div>
        )}

        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
          {actions.map((action) => {
            const Icon = action.icon;
            const count = action.count ?? getCount(action.id);
            const isDisabled =
              action.disabled || (action.requiresOnline && !isOnline);

            return (
              <Button
                key={action.id}
                variant={action.primary ? 'default' : 'outline'}
                onClick={() => handleAction(action)}
                disabled={isDisabled}
                className={cn(
                  'flex-shrink-0 gap-2 min-h-[44px]',
                  action.primary &&
                    'bg-primary text-primary-foreground shadow-md'
                )}
              >
                {action.loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Icon className="h-4 w-4" />
                )}
                <span>{action.label}</span>
                {count !== undefined && count > 0 && (
                  <Badge
                    variant={action.primary ? 'secondary' : 'destructive'}
                    className="ml-1"
                  >
                    {count > 99 ? '99+' : count}
                  </Badge>
                )}
              </Button>
            );
          })}
        </div>
      </div>
    );
  }

  // Grid variant - full card with grid layout
  return (
    <Card className={cn('', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Schnellaktionen
          </CardTitle>
          {!isOnline && (
            <Badge variant="secondary" className="gap-1">
              <WifiOff className="h-3 w-3" />
              Offline
            </Badge>
          )}
          {isOnline && showCounts && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => refetch()}
              disabled={countsLoading}
              className="h-8 w-8"
            >
              <RefreshCw
                className={cn('h-4 w-4', countsLoading && 'animate-spin')}
              />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3">
          {actions.map((action) => {
            const Icon = action.icon;
            const count = action.count ?? getCount(action.id);
            const isDisabled =
              action.disabled || (action.requiresOnline && !isOnline);

            return (
              <button
                key={action.id}
                onClick={() => handleAction(action)}
                disabled={isDisabled}
                className={cn(
                  'relative flex flex-col items-center gap-2 p-4 rounded-xl',
                  'min-h-[88px] transition-all duration-200',
                  'active:scale-95',
                  isDisabled
                    ? 'opacity-50 cursor-not-allowed'
                    : 'hover:bg-muted active:bg-muted/80',
                  action.primary &&
                    !isDisabled &&
                    'bg-primary/10 hover:bg-primary/20 active:bg-primary/30'
                )}
              >
                {/* Icon */}
                <div
                  className={cn(
                    'relative flex items-center justify-center',
                    'h-10 w-10 rounded-full',
                    action.primary
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {action.loading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Icon className="h-5 w-5" />
                  )}

                  {/* Count badge */}
                  {count !== undefined && count > 0 && (
                    <Badge
                      variant="destructive"
                      className={cn(
                        'absolute -top-1 -right-1 h-5 min-w-5 px-1',
                        'text-[10px] flex items-center justify-center'
                      )}
                    >
                      {count > 99 ? '99+' : count}
                    </Badge>
                  )}
                </div>

                {/* Label */}
                <span
                  className={cn(
                    'text-xs font-medium text-center',
                    action.primary ? 'text-primary' : 'text-foreground'
                  )}
                >
                  {action.label}
                </span>

                {/* Offline indicator for action */}
                {action.requiresOnline && !isOnline && (
                  <WifiOff className="absolute top-2 right-2 h-3 w-3 text-muted-foreground" />
                )}
              </button>
            );
          })}
        </div>

        {/* Loading state for counts */}
        {countsLoading && (
          <div className="mt-3 flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            Lade Zaehler...
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * QuickActionsFAB - Floating Action Button for primary action
 */
export interface QuickActionsFABProps {
  /** Primary action to display */
  action?: QuickActionItem;
  /** Click handler */
  onClick?: () => void;
  /** Position */
  position?: 'bottom-right' | 'bottom-center';
  /** Custom className */
  className?: string;
}

export function QuickActionsFAB({
  action = { id: 'scan', label: 'Scannen', icon: Camera, primary: true },
  onClick,
  position = 'bottom-right',
  className,
}: QuickActionsFABProps) {
  const { isOnline } = usePWA();
  const Icon = action.icon;
  const isDisabled = action.disabled || (action.requiresOnline && !isOnline);

  return (
    <Button
      size="lg"
      onClick={onClick}
      disabled={isDisabled}
      className={cn(
        'fixed z-40 h-14 w-14 rounded-full shadow-lg',
        'transition-transform active:scale-95',
        position === 'bottom-right' && 'bottom-20 right-4',
        position === 'bottom-center' && 'bottom-20 left-1/2 -translate-x-1/2',
        className
      )}
    >
      <Icon className="h-6 w-6" />
      <span className="sr-only">{action.label}</span>
    </Button>
  );
}

export default QuickActions;
