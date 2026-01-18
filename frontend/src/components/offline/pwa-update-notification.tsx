/**
 * PWAUpdateNotification Component
 *
 * Shows a notification when a new version of the app is available.
 * Features:
 * - Toast-style notification
 * - One-click update
 * - Auto-dismiss option
 */

import * as React from 'react';
import { RefreshCw, X, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePWAFeatures } from '@/lib/hooks/use-pwa-features';
import { motion, AnimatePresence } from 'framer-motion';

// ============================================
// Types
// ============================================

export interface PWAUpdateNotificationProps {
  /** Position of the notification */
  position?: 'top-right' | 'bottom-right' | 'top-left' | 'bottom-left';
  /** Auto-dismiss after X seconds (0 = never) */
  autoDismissSeconds?: number;
  /** Custom className */
  className?: string;
}

// ============================================
// Component
// ============================================

export function PWAUpdateNotification({
  position = 'bottom-right',
  autoDismissSeconds = 0,
  className,
}: PWAUpdateNotificationProps) {
  const { updateAvailable, offlineReady, updateServiceWorker } = usePWAFeatures();
  const [isDismissed, setIsDismissed] = React.useState(false);
  const [showOfflineReady, setShowOfflineReady] = React.useState(false);

  // Show offline ready message briefly
  React.useEffect(() => {
    if (offlineReady) {
      setShowOfflineReady(true);
      const timer = setTimeout(() => setShowOfflineReady(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [offlineReady]);

  // Auto-dismiss
  React.useEffect(() => {
    if (updateAvailable && autoDismissSeconds > 0 && !isDismissed) {
      const timer = setTimeout(() => {
        setIsDismissed(true);
      }, autoDismissSeconds * 1000);
      return () => clearTimeout(timer);
    }
  }, [updateAvailable, autoDismissSeconds, isDismissed]);

  // Reset dismissed state when update becomes available
  React.useEffect(() => {
    if (updateAvailable) {
      setIsDismissed(false);
    }
  }, [updateAvailable]);

  const handleUpdate = React.useCallback(() => {
    updateServiceWorker();
    // The page will reload after update
  }, [updateServiceWorker]);

  const handleDismiss = React.useCallback(() => {
    setIsDismissed(true);
  }, []);

  // Position classes
  const positionClasses = {
    'top-right': 'top-4 right-4',
    'bottom-right': 'bottom-4 right-4',
    'top-left': 'top-4 left-4',
    'bottom-left': 'bottom-4 left-4',
  };

  const showUpdate = updateAvailable && !isDismissed;

  return (
    <AnimatePresence>
      {/* Update available notification */}
      {showUpdate && (
        <motion.div
          initial={{ opacity: 0, y: position.startsWith('top') ? -20 : 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: position.startsWith('top') ? -20 : 20, scale: 0.95 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className={cn(
            'fixed z-50',
            positionClasses[position],
            className
          )}
        >
          <div className="bg-primary text-primary-foreground rounded-lg shadow-lg p-4 max-w-sm">
            <div className="flex items-start gap-3">
              <div className="bg-white/20 rounded-full p-2">
                <Download className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="font-medium">Update verfuegbar</p>
                <p className="text-sm opacity-80 mt-1">
                  Eine neue Version von Ablage-System ist bereit.
                </p>
                <div className="flex gap-2 mt-3">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleUpdate}
                    className="bg-white/20 hover:bg-white/30"
                  >
                    <RefreshCw className="h-4 w-4 mr-1" />
                    Jetzt aktualisieren
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleDismiss}
                    className="hover:bg-white/20"
                  >
                    Spaeter
                  </Button>
                </div>
              </div>
              <Button
                size="icon"
                variant="ghost"
                onClick={handleDismiss}
                className="h-6 w-6 -mt-1 -mr-1 hover:bg-white/20"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </motion.div>
      )}

      {/* Offline ready notification */}
      {showOfflineReady && !showUpdate && (
        <motion.div
          initial={{ opacity: 0, y: position.startsWith('top') ? -20 : 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: position.startsWith('top') ? -20 : 20, scale: 0.95 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          className={cn(
            'fixed z-50',
            positionClasses[position],
            className
          )}
        >
          <div className="bg-green-500 text-white rounded-lg shadow-lg p-4 max-w-sm">
            <div className="flex items-center gap-3">
              <div className="bg-white/20 rounded-full p-2">
                <Download className="h-5 w-5" />
              </div>
              <div>
                <p className="font-medium">Offline bereit</p>
                <p className="text-sm opacity-80">
                  Die App funktioniert jetzt auch ohne Internet.
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default PWAUpdateNotification;
