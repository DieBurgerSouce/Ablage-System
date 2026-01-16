/**
 * SessionTimeoutWarning - Session Timeout Warnung
 *
 * Zeigt eine modale Warnung an, wenn die Session bald abläuft.
 * Der User kann die Session verlängern oder sich ausloggen.
 *
 * Features:
 * - Countdown-Anzeige
 * - "Session verlängern" Button
 * - Auto-Logout bei Ablauf
 */

import { useState, useEffect, useCallback } from 'react';
import { Clock, RefreshCw, LogOut } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useAuth } from '@/lib/auth/AuthContext';
import { logger } from '@/lib/logger';

// ==================== Helper ====================

function formatTimeRemaining(ms: number): string {
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);

  if (minutes > 0) {
    return `${minutes}:${seconds.toString().padStart(2, '0')} Minuten`;
  }
  return `${seconds} Sekunden`;
}

// ==================== Component ====================

export function SessionTimeoutWarning() {
  const {
    sessionExpiringSoon,
    sessionTimeRemaining,
    refreshSession,
    logout,
    isAuthenticated,
  } = useAuth();

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  // Zeige Dialog wenn Session bald abläuft
  useEffect(() => {
    if (sessionExpiringSoon && isAuthenticated) {
      setIsOpen(true);
    }
  }, [sessionExpiringSoon, isAuthenticated]);

  // Session verlängern
  const handleExtendSession = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refreshSession();
      setIsOpen(false);
    } catch (error) {
      logger.error('Sitzung verlängern fehlgeschlagen', error);
    } finally {
      setIsRefreshing(false);
    }
  }, [refreshSession]);

  // Ausloggen
  const handleLogout = useCallback(() => {
    setIsOpen(false);
    logout();
  }, [logout]);

  // Berechne Fortschritt (5 Minuten = 300000ms als 100%)
  const progressValue = sessionTimeRemaining
    ? Math.max(0, Math.min(100, (sessionTimeRemaining / 300000) * 100))
    : 0;

  // Nicht rendern wenn nicht authentifiziert
  if (!isAuthenticated) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-amber-500" />
            Session läuft ab
          </DialogTitle>
          <DialogDescription>
            Ihre Sitzung läuft bald ab. Möchten Sie angemeldet bleiben?
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {/* Countdown */}
          <div className="text-center mb-4">
            <div className="text-4xl font-mono font-bold text-amber-600 dark:text-amber-400">
              {sessionTimeRemaining ? formatTimeRemaining(sessionTimeRemaining) : '0:00'}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              verbleibend
            </p>
          </div>

          {/* Progress Bar */}
          <Progress
            value={progressValue}
            className="h-2"
          />

          {/* Info Text */}
          <p className="text-sm text-muted-foreground mt-4 text-center">
            Nach Ablauf werden Sie automatisch abgemeldet.
          </p>
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={handleLogout}
            className="w-full sm:w-auto"
          >
            <LogOut className="h-4 w-4 mr-2" />
            Jetzt abmelden
          </Button>
          <Button
            onClick={handleExtendSession}
            disabled={isRefreshing}
            className="w-full sm:w-auto"
          >
            {isRefreshing ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Verlängert...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4 mr-2" />
                Session verlängern
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SessionTimeoutWarning;
