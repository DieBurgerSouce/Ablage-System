/**
 * ActiveSessionsTab - Aktive Sitzungen Verwaltung
 *
 * Zeigt alle aktiven Sitzungen des Benutzers an und ermoeglicht:
 * - Uebersicht aller aktiven Sitzungen
 * - Einzelne Sitzung beenden
 * - Alle anderen Sitzungen beenden
 *
 * Integration in SettingsModal unter "Sicherheit" Tab.
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Monitor,
  Smartphone,
  Tablet,
  Globe,
  Clock,
  MapPin,
  XCircle,
  LogOut,
  Loader2,
  AlertTriangle,
  Shield,
  CheckCircle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface Session {
  id: string;
  device_type: 'desktop' | 'mobile' | 'tablet' | 'unknown';
  browser: string;
  os: string;
  ip_address: string;
  location?: string;
  last_activity: string;
  created_at: string;
  is_current: boolean;
}

interface SessionsResponse {
  sessions: Session[];
  current_session_id: string;
}

// ==================== API ====================

async function fetchSessions(): Promise<SessionsResponse> {
  // TODO: Ersetze mit echtem API-Call wenn Backend verfuegbar
  // const response = await apiClient.get<SessionsResponse>('/auth/sessions');
  // return response.data;

  // Mock-Daten fuer Entwicklung
  await new Promise((resolve) => setTimeout(resolve, 500));

  const mockSessions: Session[] = [
    {
      id: 'session-1',
      device_type: 'desktop',
      browser: 'Chrome 120',
      os: 'Windows 11',
      ip_address: '192.168.1.100',
      location: 'Stuttgart, DE',
      last_activity: new Date().toISOString(),
      created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      is_current: true,
    },
    {
      id: 'session-2',
      device_type: 'mobile',
      browser: 'Safari 17',
      os: 'iOS 17',
      ip_address: '192.168.1.101',
      location: 'Stuttgart, DE',
      last_activity: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      is_current: false,
    },
    {
      id: 'session-3',
      device_type: 'tablet',
      browser: 'Firefox 121',
      os: 'Android 14',
      ip_address: '10.0.0.50',
      location: 'Muenchen, DE',
      last_activity: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      is_current: false,
    },
  ];

  return {
    sessions: mockSessions,
    current_session_id: 'session-1',
  };
}

async function terminateSession(sessionId: string): Promise<void> {
  // TODO: Ersetze mit echtem API-Call
  // await apiClient.delete(`/auth/sessions/${sessionId}`);
  await new Promise((resolve) => setTimeout(resolve, 300));
}

async function terminateOtherSessions(): Promise<void> {
  // TODO: Ersetze mit echtem API-Call
  // await apiClient.delete('/auth/sessions/others');
  await new Promise((resolve) => setTimeout(resolve, 500));
}

// ==================== Helpers ====================

function getDeviceIcon(deviceType: Session['device_type']) {
  switch (deviceType) {
    case 'desktop':
      return Monitor;
    case 'mobile':
      return Smartphone;
    case 'tablet':
      return Tablet;
    default:
      return Globe;
  }
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = Date.now();
  const diff = now - date.getTime();

  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Gerade eben';
  if (minutes < 60) return `Vor ${minutes} Minuten`;
  if (hours < 24) return `Vor ${hours} Stunden`;
  if (days < 7) return `Vor ${days} Tagen`;

  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

// ==================== Component ====================

export function ActiveSessionsTab() {
  const queryClient = useQueryClient();
  const [sessionToTerminate, setSessionToTerminate] = useState<string | null>(null);
  const [showTerminateAllDialog, setShowTerminateAllDialog] = useState(false);

  // Fetch sessions
  const { data, isLoading, error, isError } = useQuery({
    queryKey: ['auth-sessions'],
    queryFn: fetchSessions,
    staleTime: 30000, // 30 Sekunden
  });

  // Terminate single session mutation
  const terminateMutation = useMutation({
    mutationFn: terminateSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
      toast.success('Sitzung beendet', {
        description: 'Die Sitzung wurde erfolgreich beendet.',
      });
    },
    onError: () => {
      toast.error('Fehler', {
        description: 'Die Sitzung konnte nicht beendet werden.',
      });
    },
  });

  // Terminate all other sessions mutation
  const terminateAllMutation = useMutation({
    mutationFn: terminateOtherSessions,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-sessions'] });
      toast.success('Sitzungen beendet', {
        description: 'Alle anderen Sitzungen wurden beendet.',
      });
    },
    onError: () => {
      toast.error('Fehler', {
        description: 'Die Sitzungen konnten nicht beendet werden.',
      });
    },
  });

  const handleTerminateSession = useCallback((sessionId: string) => {
    setSessionToTerminate(sessionId);
  }, []);

  const confirmTerminateSession = useCallback(() => {
    if (sessionToTerminate) {
      terminateMutation.mutate(sessionToTerminate);
      setSessionToTerminate(null);
    }
  }, [sessionToTerminate, terminateMutation]);

  const handleTerminateAllSessions = useCallback(() => {
    setShowTerminateAllDialog(true);
  }, []);

  const confirmTerminateAllSessions = useCallback(() => {
    terminateAllMutation.mutate();
    setShowTerminateAllDialog(false);
  }, [terminateAllMutation]);

  // Loading State
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  // Error State
  if (isError) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            <span>Sitzungen konnten nicht geladen werden: {(error as Error).message}</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const sessions = data?.sessions ?? [];
  const otherSessions = sessions.filter((s) => !s.is_current);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Aktive Sitzungen
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            Verwalten Sie Ihre aktiven Anmeldesitzungen auf verschiedenen Geraeten.
          </p>
        </div>

        {otherSessions.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleTerminateAllSessions}
            disabled={terminateAllMutation.isPending}
            className="text-destructive hover:text-destructive"
          >
            {terminateAllMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <LogOut className="h-4 w-4 mr-2" />
            )}
            Alle anderen beenden
          </Button>
        )}
      </div>

      {/* Sessions List */}
      <div className="space-y-3">
        {sessions.map((session) => {
          const DeviceIcon = getDeviceIcon(session.device_type);

          return (
            <Card
              key={session.id}
              className={cn(
                'transition-colors',
                session.is_current && 'border-primary bg-primary/5'
              )}
            >
              <CardContent className="pt-4 pb-4">
                <div className="flex items-start justify-between gap-4">
                  {/* Device Info */}
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        'p-2 rounded-lg',
                        session.is_current
                          ? 'bg-primary/10 text-primary'
                          : 'bg-muted text-muted-foreground'
                      )}
                    >
                      <DeviceIcon className="h-5 w-5" />
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {session.browser} auf {session.os}
                        </span>
                        {session.is_current && (
                          <Badge variant="default" className="text-xs">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Diese Sitzung
                          </Badge>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Globe className="h-3.5 w-3.5" />
                          {session.ip_address}
                        </span>
                        {session.location && (
                          <span className="flex items-center gap-1">
                            <MapPin className="h-3.5 w-3.5" />
                            {session.location}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" />
                          {formatRelativeTime(session.last_activity)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  {!session.is_current && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleTerminateSession(session.id)}
                      disabled={terminateMutation.isPending && sessionToTerminate === session.id}
                      className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    >
                      {terminateMutation.isPending && sessionToTerminate === session.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <XCircle className="h-4 w-4" />
                      )}
                      <span className="ml-2 hidden sm:inline">Beenden</span>
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Empty State */}
      {sessions.length === 0 && (
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-muted-foreground">
              <Shield className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Keine aktiven Sitzungen gefunden.</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Info */}
      <Card className="bg-muted/30">
        <CardContent className="pt-4 pb-4">
          <p className="text-sm text-muted-foreground">
            Wenn Sie eine verdaechtige Sitzung bemerken, beenden Sie diese sofort und aendern Sie Ihr Passwort.
            Die aktuelle Sitzung kann nicht beendet werden - nutzen Sie dafuer die Abmelden-Funktion.
          </p>
        </CardContent>
      </Card>

      {/* Terminate Single Session Dialog */}
      <AlertDialog
        open={!!sessionToTerminate}
        onOpenChange={(open) => !open && setSessionToTerminate(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Sitzung beenden?</AlertDialogTitle>
            <AlertDialogDescription>
              Diese Sitzung wird sofort beendet. Das Geraet muss sich erneut anmelden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmTerminateSession}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Sitzung beenden
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Terminate All Sessions Dialog */}
      <AlertDialog
        open={showTerminateAllDialog}
        onOpenChange={setShowTerminateAllDialog}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Alle anderen Sitzungen beenden?</AlertDialogTitle>
            <AlertDialogDescription>
              Alle anderen Geraete werden sofort abgemeldet. Nur diese aktuelle Sitzung bleibt aktiv.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmTerminateAllSessions}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Alle beenden
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ActiveSessionsTab;
