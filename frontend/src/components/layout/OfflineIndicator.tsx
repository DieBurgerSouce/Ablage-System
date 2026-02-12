/**
 * OfflineIndicator - Netzwerk-Status Banner
 *
 * Zeigt einen Banner wenn der Browser offline ist.
 * Verschwindet automatisch nach Wiederherstellung der Verbindung.
 *
 * Features:
 * - Animierter Ein-/Ausblend-Effekt
 * - Kurze Verzögerung nach Reconnect bevor Banner verschwindet
 * - WCAG 2.1 AA konform (role="alert")
 * - Alle Texte auf Deutsch
 */

import { memo, useState, useEffect } from 'react';
import { WifiOff, Wifi } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useOnlineStatus } from '@/hooks/use-online-status';

function OfflineIndicatorInner({ className }: { className?: string }) {
  const { isOffline, isOnline } = useOnlineStatus();
  const [visible, setVisible] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);
  const [showReconnected, setShowReconnected] = useState(false);

  useEffect(() => {
    if (isOffline) {
      setVisible(true);
      setWasOffline(true);
      setShowReconnected(false);
    } else if (wasOffline && isOnline) {
      // Zeige "Wieder verbunden" kurz an
      setShowReconnected(true);
      const timer = setTimeout(() => {
        setVisible(false);
        setWasOffline(false);
        setShowReconnected(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [isOffline, isOnline, wasOffline]);

  if (!visible) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        'flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium transition-all duration-300',
        showReconnected
          ? 'bg-green-600 text-white'
          : 'bg-amber-600 text-white',
        className,
      )}
    >
      {showReconnected ? (
        <>
          <Wifi className="h-4 w-4" aria-hidden="true" />
          <span>Verbindung wiederhergestellt</span>
        </>
      ) : (
        <>
          <WifiOff className="h-4 w-4" aria-hidden="true" />
          <span>Keine Internetverbindung - Offline-Modus aktiv</span>
        </>
      )}
    </div>
  );
}

export const OfflineIndicator = memo(OfflineIndicatorInner);
