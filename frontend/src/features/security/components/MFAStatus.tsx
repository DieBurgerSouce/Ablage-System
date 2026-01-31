/**
 * MFA Status Component
 *
 * Zeigt den aktuellen 2FA-Status und ermoeglicht Verwaltungsaktionen:
 * - Status-Anzeige (aktiviert/deaktiviert)
 * - Backup-Codes regenerieren
 * - 2FA deaktivieren
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  ShieldCheck,
  ShieldOff,
  Key,
  RefreshCw,
  Trash2,
  Loader2,
  AlertTriangle,
  Copy,
  Download,
  CheckCircle2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

import { authService } from '@/lib/api/services/auth';

interface MFAStatusProps {
  onSetupClick: () => void;
}

export function MFAStatus({ onSetupClick }: MFAStatusProps) {
  const [showDisableDialog, setShowDisableDialog] = useState(false);
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);
  const [confirmCode, setConfirmCode] = useState('');
  const [newBackupCodes, setNewBackupCodes] = useState<string[] | null>(null);

  const queryClient = useQueryClient();

  // Fetch MFA status
  const { data: status, isLoading, error } = useQuery({
    queryKey: ['mfa-status'],
    queryFn: () => authService.get2FAStatus(),
    staleTime: 30000, // 30 seconds
  });

  // Disable 2FA mutation
  const disableMutation = useMutation({
    mutationFn: (code: string) => authService.disable2FA(code),
    onSuccess: () => {
      toast.success('2FA wurde deaktiviert');
      queryClient.invalidateQueries({ queryKey: ['mfa-status'] });
      setShowDisableDialog(false);
      setConfirmCode('');
    },
    onError: () => {
      toast.error('Ungueltiger Code', {
        description: 'Bitte pruefen Sie den Code und versuchen Sie es erneut.',
      });
      setConfirmCode('');
    },
  });

  // Regenerate backup codes mutation
  const regenerateMutation = useMutation({
    mutationFn: (code: string) => authService.regenerateBackupCodes(code),
    onSuccess: (codes) => {
      setNewBackupCodes(codes);
      queryClient.invalidateQueries({ queryKey: ['mfa-status'] });
      setConfirmCode('');
    },
    onError: () => {
      toast.error('Ungueltiger Code', {
        description: 'Bitte pruefen Sie den Code und versuchen Sie es erneut.',
      });
      setConfirmCode('');
    },
  });

  // Copy backup codes
  const copyBackupCodes = () => {
    if (!newBackupCodes) return;
    const text = newBackupCodes.join('\n');
    navigator.clipboard.writeText(text);
    toast.success('Backup-Codes kopiert');
  };

  // Download backup codes
  const downloadBackupCodes = () => {
    if (!newBackupCodes) return;
    const text = `Ablage-System 2FA Backup-Codes
==============================

WICHTIG: Diese Codes sind einmalig verwendbar!
Speichern Sie sie an einem sicheren Ort.

${newBackupCodes.map((code, i) => `${i + 1}. ${code}`).join('\n')}

Generiert am: ${new Date().toLocaleString('de-DE')}
`;
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ablage-system-backup-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Backup-Codes heruntergeladen');
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Fehler</AlertTitle>
            <AlertDescription>
              Der MFA-Status konnte nicht geladen werden.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Zwei-Faktor-Authentifizierung</CardTitle>
            </div>
            <Badge variant={status?.enabled ? 'default' : 'secondary'}>
              {status?.enabled ? (
                <>
                  <ShieldCheck className="mr-1 h-3 w-3" />
                  Aktiviert
                </>
              ) : (
                <>
                  <ShieldOff className="mr-1 h-3 w-3" />
                  Deaktiviert
                </>
              )}
            </Badge>
          </div>
          <CardDescription>
            Schuetzen Sie Ihr Konto mit einem zusaetzlichen Sicherheitsfaktor
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {status?.enabled ? (
            <>
              {/* Status info */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                  <div>
                    <p className="text-sm font-medium">Aktiviert seit</p>
                    <p className="text-sm text-muted-foreground">
                      {status.setup_at
                        ? new Date(status.setup_at).toLocaleDateString('de-DE', {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric',
                          })
                        : 'Unbekannt'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
                  <Key className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="text-sm font-medium">Backup-Codes</p>
                    <p className="text-sm text-muted-foreground">
                      {status.backup_codes_remaining} von 10 verbleibend
                    </p>
                  </div>
                </div>
              </div>

              {/* Warning if low backup codes */}
              {status.backup_codes_remaining <= 3 && (
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>Wenige Backup-Codes verbleibend</AlertTitle>
                  <AlertDescription>
                    Sie haben nur noch {status.backup_codes_remaining} Backup-Codes. Generieren Sie neue Codes, um den Zugang zu Ihrem Konto zu sichern.
                  </AlertDescription>
                </Alert>
              )}

              {/* Actions */}
              <div className="flex flex-col sm:flex-row gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setShowRegenerateDialog(true)}
                  className="flex-1"
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Backup-Codes erneuern
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowDisableDialog(true)}
                  className="flex-1 text-destructive hover:text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  2FA deaktivieren
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Zwei-Faktor-Authentifizierung (2FA) fuegt Ihrem Konto eine zusaetzliche Sicherheitsebene hinzu.
                Bei der Anmeldung benoetigen Sie neben Ihrem Passwort einen Code aus Ihrer Authenticator-App.
              </p>
              <Button onClick={onSetupClick}>
                <Shield className="mr-2 h-4 w-4" />
                2FA einrichten
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      {/* Disable 2FA Dialog */}
      <Dialog open={showDisableDialog} onOpenChange={setShowDisableDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>2FA deaktivieren</DialogTitle>
            <DialogDescription>
              Geben Sie einen Code aus Ihrer Authenticator-App ein, um die Zwei-Faktor-Authentifizierung zu deaktivieren.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Warnung</AlertTitle>
              <AlertDescription>
                Nach der Deaktivierung ist Ihr Konto nur noch durch Ihr Passwort geschützt.
              </AlertDescription>
            </Alert>
            <Input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              placeholder="000000"
              value={confirmCode}
              onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, ''))}
              className="text-center text-xl tracking-widest font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDisableDialog(false)}>
              Abbrechen
            </Button>
            <Button
              variant="destructive"
              onClick={() => disableMutation.mutate(confirmCode)}
              disabled={confirmCode.length !== 6 || disableMutation.isPending}
            >
              {disableMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Deaktivieren
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Regenerate Backup Codes Dialog */}
      <Dialog open={showRegenerateDialog} onOpenChange={(open) => {
        setShowRegenerateDialog(open);
        if (!open) {
          setNewBackupCodes(null);
          setConfirmCode('');
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Backup-Codes erneuern</DialogTitle>
            <DialogDescription>
              {newBackupCodes
                ? 'Hier sind Ihre neuen Backup-Codes. Speichern Sie sie an einem sicheren Ort.'
                : 'Geben Sie einen Code aus Ihrer Authenticator-App ein, um neue Backup-Codes zu generieren.'}
            </DialogDescription>
          </DialogHeader>

          {newBackupCodes ? (
            <div className="py-4 space-y-4">
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Wichtig!</AlertTitle>
                <AlertDescription>
                  Die alten Backup-Codes sind nicht mehr gueltig. Speichern Sie die neuen Codes sicher ab.
                </AlertDescription>
              </Alert>
              <div className="grid grid-cols-2 gap-2 p-4 bg-muted/50 rounded-lg font-mono text-sm">
                {newBackupCodes.map((code, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Badge variant="outline" className="w-6 justify-center">
                      {index + 1}
                    </Badge>
                    <span>{code}</span>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={copyBackupCodes} className="flex-1">
                  <Copy className="mr-2 h-4 w-4" />
                  Kopieren
                </Button>
                <Button variant="outline" onClick={downloadBackupCodes} className="flex-1">
                  <Download className="mr-2 h-4 w-4" />
                  Herunterladen
                </Button>
              </div>
            </div>
          ) : (
            <div className="py-4">
              <Alert className="mb-4">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Hinweis</AlertTitle>
                <AlertDescription>
                  Nach der Generierung werden alle bestehenden Backup-Codes ungueltig.
                </AlertDescription>
              </Alert>
              <Input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                placeholder="000000"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, ''))}
                className="text-center text-xl tracking-widest font-mono"
                autoFocus
              />
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowRegenerateDialog(false);
              setNewBackupCodes(null);
              setConfirmCode('');
            }}>
              {newBackupCodes ? 'Schliessen' : 'Abbrechen'}
            </Button>
            {!newBackupCodes && (
              <Button
                onClick={() => regenerateMutation.mutate(confirmCode)}
                disabled={confirmCode.length !== 6 || regenerateMutation.isPending}
              >
                {regenerateMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Codes generieren
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
