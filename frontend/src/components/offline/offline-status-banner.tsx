/**
 * OfflineStatusBanner Component
 *
 * Visual indicator for offline status and sync progress.
 * Features:
 * - Slide-in animation when offline
 * - Sync progress display
 * - Manual sync trigger
 * - Pending mutation count
 */

import * as React from 'react';
import { WifiOff, Wifi, CloudOff, RefreshCw, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useOfflineSync } from '@/lib/offline';
import { motion, AnimatePresence } from 'framer-motion';

// ============================================
// Types
// ============================================

export interface OfflineStatusBannerProps {
  /** Position of the banner */
  position?: 'top' | 'bottom';
  /** Custom className */
  className?: string;
  /** Show sync button (default: true) */
  showSyncButton?: boolean;
  /** Show pending count (default: true) */
  showPendingCount?: boolean;
  /** Compact mode for mobile */
  compact?: boolean;
}

// ============================================
// Component
// ============================================

export function OfflineStatusBanner({
  position = 'bottom',
  className,
  showSyncButton = true,
  showPendingCount = true,
  compact = false,
}: OfflineStatusBannerProps) {
  const { progress, pendingCount, isSyncing, isOnline, sync } = useOfflineSync({
    autoSync: true,
    onSyncComplete: (result) => {
      // Could show toast here
    },
  });

  const [showSuccess, setShowSuccess] = React.useState(false);

  // Show success message briefly after sync completes
  React.useEffect(() => {
    if (progress.status === 'completed' && progress.succeeded > 0) {
      setShowSuccess(true);
      const timer = setTimeout(() => setShowSuccess(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [progress.status, progress.succeeded]);

  // Don't show banner if online and no pending items
  const shouldShow = !isOnline || pendingCount > 0 || isSyncing || showSuccess;

  const handleSync = React.useCallback(async () => {
    await sync();
  }, [sync]);

  return (
    <AnimatePresence>
      {shouldShow && (
        <motion.div
          initial={{ y: position === 'top' ? -100 : 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: position === 'top' ? -100 : 100, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className={cn(
            'fixed left-0 right-0 z-50 px-4 py-2',
            position === 'top' ? 'top-0' : 'bottom-0',
            className
          )}
        >
          <div
            className={cn(
              'mx-auto max-w-lg rounded-lg shadow-lg',
              !isOnline
                ? 'bg-destructive text-destructive-foreground'
                : showSuccess
                ? 'bg-green-500 text-white'
                : 'bg-yellow-500 text-yellow-950',
              compact ? 'px-3 py-2' : 'px-4 py-3'
            )}
          >
            {/* Main status row */}
            <div className="flex items-center justify-between gap-3">
              {/* Status icon and text */}
              <div className="flex items-center gap-2">
                {!isOnline ? (
                  <>
                    <WifiOff className={cn('shrink-0', compact ? 'h-4 w-4' : 'h-5 w-5')} />
                    <span className={cn('font-medium', compact ? 'text-sm' : '')}>
                      Offline
                    </span>
                  </>
                ) : isSyncing ? (
                  <>
                    <Loader2
                      className={cn(
                        'shrink-0 animate-spin',
                        compact ? 'h-4 w-4' : 'h-5 w-5'
                      )}
                    />
                    <span className={cn('font-medium', compact ? 'text-sm' : '')}>
                      Synchronisiere...
                    </span>
                  </>
                ) : showSuccess ? (
                  <>
                    <Check className={cn('shrink-0', compact ? 'h-4 w-4' : 'h-5 w-5')} />
                    <span className={cn('font-medium', compact ? 'text-sm' : '')}>
                      Synchronisiert
                    </span>
                  </>
                ) : pendingCount > 0 ? (
                  <>
                    <CloudOff className={cn('shrink-0', compact ? 'h-4 w-4' : 'h-5 w-5')} />
                    <span className={cn('font-medium', compact ? 'text-sm' : '')}>
                      {pendingCount} ausstehend
                    </span>
                  </>
                ) : (
                  <>
                    <Wifi className={cn('shrink-0', compact ? 'h-4 w-4' : 'h-5 w-5')} />
                    <span className={cn('font-medium', compact ? 'text-sm' : '')}>
                      Online
                    </span>
                  </>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                {showPendingCount && pendingCount > 0 && !compact && (
                  <span className="text-sm opacity-80">
                    {pendingCount} {pendingCount === 1 ? 'Änderung' : 'Änderungen'}
                  </span>
                )}

                {showSyncButton && isOnline && pendingCount > 0 && !isSyncing && (
                  <Button
                    size={compact ? 'sm' : 'default'}
                    variant="secondary"
                    onClick={handleSync}
                    className={cn(
                      'bg-white/20 hover:bg-white/30',
                      compact && 'h-7 px-2'
                    )}
                  >
                    <RefreshCw className={cn('mr-1', compact ? 'h-3 w-3' : 'h-4 w-4')} />
                    {compact ? 'Sync' : 'Jetzt synchronisieren'}
                  </Button>
                )}
              </div>
            </div>

            {/* Sync progress bar */}
            {isSyncing && progress.total > 0 && (
              <div className="mt-2">
                <Progress
                  value={(progress.processed / progress.total) * 100}
                  className="h-1.5 bg-white/20"
                />
                <p className="text-xs mt-1 opacity-80">
                  {progress.processed} von {progress.total} synchronisiert
                  {progress.failed > 0 && ` (${progress.failed} fehlgeschlagen)`}
                </p>
              </div>
            )}

            {/* Offline info */}
            {!isOnline && !compact && (
              <p className="text-sm mt-1 opacity-80">
                Änderungen werden gespeichert und automatisch synchronisiert.
              </p>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default OfflineStatusBanner;
