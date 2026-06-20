/**
 * MFA Setup Component
 *
 * Multi-step wizard for setting up TOTP-based 2FA:
 * 1. QR-Code scannen oder Secret manuell eingeben
 * 2. Code aus Authenticator-App eingeben
 * 3. Backup-Codes sicher speichern
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield,
  Smartphone,
  Key,
  CheckCircle2,
  Copy,
  Download,
  AlertTriangle,
  Loader2,
  Eye,
  EyeOff,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

import { authService, type TwoFactorSetupResponse } from '@/lib/api/services/auth';

/** Extrahiert das TOTP-Secret aus der otpauth-Provisioning-URI (fuer manuelle Eingabe). */
function extractTotpSecret(provisioningUri: string): string {
  return provisioningUri.split('secret=')[1]?.split('&')[0] ?? '';
}

interface MFASetupProps {
  onComplete: () => void;
  onCancel: () => void;
}

type SetupStep = 'intro' | 'scan' | 'verify' | 'backup' | 'complete';

export function MFASetup({ onComplete, onCancel }: MFASetupProps) {
  const [step, setStep] = useState<SetupStep>('intro');
  const [setupData, setSetupData] = useState<TwoFactorSetupResponse | null>(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [showSecret, setShowSecret] = useState(false);
  const [backupCodesCopied, setBackupCodesCopied] = useState(false);

  const queryClient = useQueryClient();

  // Start 2FA setup
  const setupMutation = useMutation({
    mutationFn: () => authService.setup2FA(),
    onSuccess: (data) => {
      setSetupData(data);
      setStep('scan');
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Starten des 2FA-Setups', {
        description: error.message,
      });
    },
  });

  // Verify TOTP code
  const verifyMutation = useMutation({
    mutationFn: (code: string) => authService.verify2FASetup(code),
    onSuccess: () => {
      setStep('backup');
    },
    onError: () => {
      toast.error('Ungültiger Code', {
        description: 'Bitte prüfen Sie den Code und versuchen Sie es erneut.',
      });
      setVerifyCode('');
    },
  });

  // Handle verify submission
  const handleVerify = () => {
    if (verifyCode.length !== 6) {
      toast.error('Bitte geben Sie einen 6-stelligen Code ein');
      return;
    }
    verifyMutation.mutate(verifyCode);
  };

  // Copy backup codes to clipboard
  const copyBackupCodes = () => {
    if (!setupData?.backup_codes) return;
    const text = setupData.backup_codes.join('\n');
    navigator.clipboard.writeText(text);
    setBackupCodesCopied(true);
    toast.success('Backup-Codes in Zwischenablage kopiert');
  };

  // Download backup codes as text file
  const downloadBackupCodes = () => {
    if (!setupData?.backup_codes) return;
    const text = `Ablage-System 2FA Backup-Codes
==============================

WICHTIG: Diese Codes sind einmalig verwendbar!
Speichern Sie sie an einem sicheren Ort.

${setupData.backup_codes.map((code, i) => `${i + 1}. ${code}`).join('\n')}

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

  // Complete setup
  const completeSetup = () => {
    queryClient.invalidateQueries({ queryKey: ['mfa-status'] });
    setStep('complete');
  };

  return (
    <Card className="w-full max-w-lg mx-auto">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Shield className="h-6 w-6 text-primary" />
          <CardTitle>Zwei-Faktor-Authentifizierung einrichten</CardTitle>
        </div>
        <CardDescription>
          Schützen Sie Ihr Konto mit einem zusätzlichen Sicherheitsfaktor
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AnimatePresence mode="wait">
          {/* Step 1: Introduction */}
          {step === 'intro' && (
            <motion.div
              key="intro"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              <div className="flex items-start gap-3 p-4 bg-muted/50 rounded-lg">
                <Smartphone className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="font-medium">Was Sie benötigen:</p>
                  <p className="text-sm text-muted-foreground">
                    Eine Authenticator-App wie Google Authenticator, Microsoft Authenticator oder Authy
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3 p-4 bg-muted/50 rounded-lg">
                <Key className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="font-medium">Wie es funktioniert:</p>
                  <p className="text-sm text-muted-foreground">
                    Sie scannen einen QR-Code mit Ihrer App und erhalten dann alle 30 Sekunden einen neuen 6-stelligen Code
                  </p>
                </div>
              </div>

              <div className="flex gap-2 pt-4">
                <Button variant="outline" onClick={onCancel} className="flex-1">
                  Abbrechen
                </Button>
                <Button
                  onClick={() => setupMutation.mutate()}
                  disabled={setupMutation.isPending}
                  className="flex-1"
                >
                  {setupMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Setup starten
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 2: Scan QR Code */}
          {step === 'scan' && setupData && (
            <motion.div
              key="scan"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              <div className="text-center">
                <p className="text-sm text-muted-foreground mb-4">
                  Scannen Sie diesen QR-Code mit Ihrer Authenticator-App
                </p>
                <div className="inline-block p-4 bg-white rounded-lg shadow-sm">
                  <img
                    src={setupData.qr_code}
                    alt="2FA QR-Code"
                    className="w-48 h-48"
                  />
                </div>
              </div>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">
                    oder manuell eingeben
                  </span>
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Secret Key</label>
                {/* Backend liefert kein Klartext-secret-Feld mehr —
                    Secret steckt im provisioning_uri (otpauth://...?secret=...) */}
                <div className="flex gap-2">
                  <Input
                    type={showSecret ? 'text' : 'password'}
                    value={extractTotpSecret(setupData.provisioning_uri)}
                    readOnly
                    className="font-mono text-sm"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setShowSecret(!showSecret)}
                  >
                    {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => {
                      navigator.clipboard.writeText(extractTotpSecret(setupData.provisioning_uri));
                      toast.success('Secret kopiert');
                    }}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="flex gap-2 pt-4">
                <Button variant="outline" onClick={onCancel}>
                  Abbrechen
                </Button>
                <Button onClick={() => setStep('verify')} className="flex-1">
                  Weiter zur Verifizierung
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 3: Verify Code */}
          {step === 'verify' && (
            <motion.div
              key="verify"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              <p className="text-sm text-muted-foreground">
                Geben Sie den 6-stelligen Code aus Ihrer Authenticator-App ein, um die Einrichtung abzuschließen.
              </p>

              <div className="space-y-2">
                <label className="text-sm font-medium">Verifizierungscode</label>
                <Input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="000000"
                  value={verifyCode}
                  onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, ''))}
                  className="text-center text-2xl tracking-widest font-mono"
                  autoFocus
                />
              </div>

              <div className="flex gap-2 pt-4">
                <Button variant="outline" onClick={() => setStep('scan')}>
                  Zurück
                </Button>
                <Button
                  onClick={handleVerify}
                  disabled={verifyCode.length !== 6 || verifyMutation.isPending}
                  className="flex-1"
                >
                  {verifyMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Verifizieren
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 4: Backup Codes */}
          {step === 'backup' && setupData && (
            <motion.div
              key="backup"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-4"
            >
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Wichtig!</AlertTitle>
                <AlertDescription>
                  Diese Backup-Codes werden nur einmal angezeigt. Speichern Sie sie an einem sicheren Ort.
                </AlertDescription>
              </Alert>

              <div className="grid grid-cols-2 gap-2 p-4 bg-muted/50 rounded-lg font-mono text-sm">
                {setupData.backup_codes.map((code, index) => (
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

              <div className="flex gap-2 pt-4">
                <Button
                  onClick={completeSetup}
                  disabled={!backupCodesCopied}
                  className="w-full"
                >
                  {backupCodesCopied ? (
                    <>
                      <CheckCircle2 className="mr-2 h-4 w-4" />
                      Einrichtung abschließen
                    </>
                  ) : (
                    'Bitte Codes zuerst kopieren oder herunterladen'
                  )}
                </Button>
              </div>
            </motion.div>
          )}

          {/* Step 5: Complete */}
          {step === 'complete' && (
            <motion.div
              key="complete"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center space-y-4 py-4"
            >
              <div className="mx-auto w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle2 className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">2FA erfolgreich aktiviert!</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Ihr Konto ist jetzt durch Zwei-Faktor-Authentifizierung geschützt.
                </p>
              </div>
              <Button onClick={onComplete} className="w-full">
                Fertig
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
