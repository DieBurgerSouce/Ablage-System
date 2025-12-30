/**
 * Sicherheits-Einstellungen Tab.
 *
 * Enthält:
 * - 2FA Status anzeigen
 * - 2FA Setup mit QR-Code
 * - 2FA deaktivieren
 * - Backup-Codes regenerieren
 */

import { useState, useEffect } from 'react';
import { Loader2, ShieldCheck, ShieldOff, KeyRound, AlertTriangle, QrCode, Copy, Check, RefreshCw } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/components/ui/use-toast';
import {
    authService,
    type TwoFactorStatus,
    type TwoFactorSetupResponse
} from '@/lib/api/services/auth';

export function SecuritySettingsTab() {
    const { toast } = useToast();

    // 2FA Status
    const [status, setStatus] = useState<TwoFactorStatus | null>(null);
    const [isLoadingStatus, setIsLoadingStatus] = useState(true);

    // Setup state
    const [isSettingUp, setIsSettingUp] = useState(false);
    const [setupData, setSetupData] = useState<TwoFactorSetupResponse | null>(null);
    const [verifyCode, setVerifyCode] = useState('');
    const [isVerifying, setIsVerifying] = useState(false);

    // Disable state
    const [disableCode, setDisableCode] = useState('');
    const [isDisabling, setIsDisabling] = useState(false);

    // Regenerate backup codes state
    const [regenerateCode, setRegenerateCode] = useState('');
    const [isRegenerating, setIsRegenerating] = useState(false);
    const [newBackupCodes, setNewBackupCodes] = useState<string[] | null>(null);

    // Copy state
    const [copiedCodes, setCopiedCodes] = useState(false);

    useEffect(() => {
        load2FAStatus();
    }, []);

    const load2FAStatus = async () => {
        setIsLoadingStatus(true);
        try {
            const data = await authService.get2FAStatus();
            setStatus(data);
        } catch (error) {
            console.error('Failed to load 2FA status:', error);
            toast({
                title: 'Fehler',
                description: '2FA-Status konnte nicht geladen werden.',
                variant: 'destructive',
            });
        } finally {
            setIsLoadingStatus(false);
        }
    };

    const handleStartSetup = async () => {
        setIsSettingUp(true);
        try {
            const data = await authService.setup2FA();
            setSetupData(data);
        } catch (error) {
            console.error('Failed to start 2FA setup:', error);
            toast({
                title: 'Fehler',
                description: '2FA-Setup konnte nicht gestartet werden.',
                variant: 'destructive',
            });
        } finally {
            setIsSettingUp(false);
        }
    };

    const handleVerifySetup = async () => {
        if (verifyCode.length < 6) return;

        setIsVerifying(true);
        try {
            await authService.verify2FASetup(verifyCode);
            toast({
                title: '2FA aktiviert',
                description: 'Zwei-Faktor-Authentifizierung wurde erfolgreich aktiviert.',
            });
            setSetupData(null);
            setVerifyCode('');
            await load2FAStatus();
        } catch (error) {
            console.error('Failed to verify 2FA setup:', error);
            toast({
                title: 'Fehler',
                description: 'Ungültiger Code. Bitte versuchen Sie es erneut.',
                variant: 'destructive',
            });
        } finally {
            setIsVerifying(false);
        }
    };

    const handleDisable2FA = async () => {
        if (disableCode.length < 6) return;

        setIsDisabling(true);
        try {
            await authService.disable2FA(disableCode);
            toast({
                title: '2FA deaktiviert',
                description: 'Zwei-Faktor-Authentifizierung wurde deaktiviert.',
            });
            setDisableCode('');
            await load2FAStatus();
        } catch (error) {
            console.error('Failed to disable 2FA:', error);
            toast({
                title: 'Fehler',
                description: 'Ungültiger Code. 2FA konnte nicht deaktiviert werden.',
                variant: 'destructive',
            });
        } finally {
            setIsDisabling(false);
        }
    };

    const handleRegenerateBackupCodes = async () => {
        if (regenerateCode.length < 6) return;

        setIsRegenerating(true);
        try {
            const codes = await authService.regenerateBackupCodes(regenerateCode);
            setNewBackupCodes(codes);
            setRegenerateCode('');
            toast({
                title: 'Backup-Codes generiert',
                description: 'Neue Backup-Codes wurden erstellt. Speichern Sie diese sicher!',
            });
            await load2FAStatus();
        } catch (error) {
            console.error('Failed to regenerate backup codes:', error);
            toast({
                title: 'Fehler',
                description: 'Ungültiger Code. Backup-Codes konnten nicht generiert werden.',
                variant: 'destructive',
            });
        } finally {
            setIsRegenerating(false);
        }
    };

    const copyBackupCodes = (codes: string[]) => {
        navigator.clipboard.writeText(codes.join('\n'));
        setCopiedCodes(true);
        setTimeout(() => setCopiedCodes(false), 2000);
        toast({
            title: 'Kopiert',
            description: 'Backup-Codes wurden in die Zwischenablage kopiert.',
        });
    };

    if (isLoadingStatus) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Setup Flow - Show QR Code and verification
    if (setupData) {
        return (
            <div className="space-y-6">
                <div className="space-y-4">
                    <h3 className="text-sm font-medium flex items-center gap-2">
                        <QrCode className="w-4 h-4" />
                        2FA einrichten
                    </h3>

                    <div className="space-y-4 p-4 rounded-lg bg-muted/50">
                        <div className="flex flex-col items-center gap-4">
                            <p className="text-sm text-center text-muted-foreground">
                                Scannen Sie diesen QR-Code mit Ihrer Authenticator-App
                                (z.B. Google Authenticator, Authy, 1Password)
                            </p>

                            {/* QR Code */}
                            <div className="p-4 bg-white rounded-lg">
                                <img
                                    src={setupData.qr_code}
                                    alt="2FA QR Code"
                                    className="w-48 h-48"
                                />
                            </div>

                            <p className="text-xs text-muted-foreground text-center">
                                Oder geben Sie diesen Code manuell ein:<br />
                                <code className="text-xs bg-muted px-2 py-1 rounded select-all">
                                    {setupData.provisioning_uri.split('secret=')[1]?.split('&')[0]}
                                </code>
                            </p>
                        </div>
                    </div>

                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>Backup-Codes speichern!</AlertTitle>
                        <AlertDescription>
                            Speichern Sie diese Codes sicher. Sie werden nur einmal angezeigt und können verwendet werden,
                            wenn Sie keinen Zugang zu Ihrer Authenticator-App haben.
                        </AlertDescription>
                    </Alert>

                    <div className="p-4 rounded-lg bg-muted/50">
                        <div className="flex items-center justify-between mb-2">
                            <Label className="text-sm font-medium">Backup-Codes</Label>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => copyBackupCodes(setupData.backup_codes)}
                            >
                                {copiedCodes ? (
                                    <Check className="w-4 h-4 mr-1" />
                                ) : (
                                    <Copy className="w-4 h-4 mr-1" />
                                )}
                                Kopieren
                            </Button>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                            {setupData.backup_codes.map((code, index) => (
                                <code key={index} className="text-sm font-mono bg-background px-3 py-2 rounded text-center">
                                    {code}
                                </code>
                            ))}
                        </div>
                    </div>

                    <Separator />

                    <div className="space-y-3">
                        <Label htmlFor="verify-code">Bestätigungscode eingeben</Label>
                        <p className="text-xs text-muted-foreground">
                            Geben Sie den 6-stelligen Code aus Ihrer Authenticator-App ein.
                        </p>
                        <div className="flex gap-3">
                            <Input
                                id="verify-code"
                                type="text"
                                inputMode="numeric"
                                maxLength={6}
                                placeholder="000000"
                                value={verifyCode}
                                onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, ''))}
                                className="font-mono text-center text-lg tracking-widest"
                            />
                            <Button
                                onClick={handleVerifySetup}
                                disabled={verifyCode.length < 6 || isVerifying}
                            >
                                {isVerifying && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                Bestätigen
                            </Button>
                        </div>
                    </div>

                    <Button
                        variant="ghost"
                        className="w-full"
                        onClick={() => setSetupData(null)}
                    >
                        Abbrechen
                    </Button>
                </div>
            </div>
        );
    }

    // Show new backup codes after regeneration
    if (newBackupCodes) {
        return (
            <div className="space-y-6">
                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Neue Backup-Codes!</AlertTitle>
                    <AlertDescription>
                        Die alten Codes sind jetzt ungültig. Speichern Sie diese neuen Codes sicher.
                    </AlertDescription>
                </Alert>

                <div className="p-4 rounded-lg bg-muted/50">
                    <div className="flex items-center justify-between mb-2">
                        <Label className="text-sm font-medium">Neue Backup-Codes</Label>
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => copyBackupCodes(newBackupCodes)}
                        >
                            {copiedCodes ? (
                                <Check className="w-4 h-4 mr-1" />
                            ) : (
                                <Copy className="w-4 h-4 mr-1" />
                            )}
                            Kopieren
                        </Button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        {newBackupCodes.map((code, index) => (
                            <code key={index} className="text-sm font-mono bg-background px-3 py-2 rounded text-center">
                                {code}
                            </code>
                        ))}
                    </div>
                </div>

                <Button
                    className="w-full"
                    onClick={() => setNewBackupCodes(null)}
                >
                    Fertig
                </Button>
            </div>
        );
    }

    // Main 2FA Status View
    return (
        <div className="space-y-6">
            {/* 2FA Status Section */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium flex items-center gap-2">
                    <KeyRound className="w-4 h-4" />
                    Zwei-Faktor-Authentifizierung (2FA)
                </h3>

                <div className="p-4 rounded-lg border">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            {status?.enabled ? (
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-500/10">
                                    <ShieldCheck className="h-5 w-5 text-green-500" />
                                </div>
                            ) : (
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                                    <ShieldOff className="h-5 w-5 text-muted-foreground" />
                                </div>
                            )}
                            <div>
                                <p className="font-medium">
                                    {status?.enabled ? '2FA ist aktiviert' : '2FA ist deaktiviert'}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {status?.enabled
                                        ? `Aktiviert am ${new Date(status.setup_at || '').toLocaleDateString('de-DE')}`
                                        : 'Schützen Sie Ihr Konto mit einem zusätzlichen Sicherheitsfaktor'}
                                </p>
                            </div>
                        </div>

                        {!status?.enabled ? (
                            <Button onClick={handleStartSetup} disabled={isSettingUp}>
                                {isSettingUp && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                Aktivieren
                            </Button>
                        ) : null}
                    </div>
                </div>

                {!status?.available && (
                    <Alert>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>
                            2FA ist auf diesem Server nicht verfügbar. Kontaktieren Sie den Administrator.
                        </AlertDescription>
                    </Alert>
                )}
            </div>

            {status?.enabled && (
                <>
                    <Separator />

                    {/* Backup Codes Status */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-medium flex items-center gap-2">
                            <RefreshCw className="w-4 h-4" />
                            Backup-Codes
                        </h3>

                        <div className="p-4 rounded-lg border">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-medium">
                                        {status.backup_codes_remaining} Backup-Codes verfügbar
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        Backup-Codes können verwendet werden, wenn Sie keinen Zugang zu Ihrer Authenticator-App haben.
                                    </p>
                                </div>

                                <AlertDialog>
                                    <AlertDialogTrigger asChild>
                                        <Button variant="outline" size="sm">
                                            <RefreshCw className="w-4 h-4 mr-2" />
                                            Neu generieren
                                        </Button>
                                    </AlertDialogTrigger>
                                    <AlertDialogContent>
                                        <AlertDialogHeader>
                                            <AlertDialogTitle>Backup-Codes neu generieren?</AlertDialogTitle>
                                            <AlertDialogDescription className="space-y-4">
                                                <p>
                                                    Alle bisherigen Backup-Codes werden ungültig.
                                                    Geben Sie Ihren aktuellen 2FA-Code zur Bestätigung ein.
                                                </p>
                                                <Input
                                                    type="text"
                                                    inputMode="numeric"
                                                    maxLength={6}
                                                    placeholder="000000"
                                                    value={regenerateCode}
                                                    onChange={(e) => setRegenerateCode(e.target.value.replace(/\D/g, ''))}
                                                    className="font-mono text-center text-lg tracking-widest"
                                                />
                                            </AlertDialogDescription>
                                        </AlertDialogHeader>
                                        <AlertDialogFooter>
                                            <AlertDialogCancel onClick={() => setRegenerateCode('')}>
                                                Abbrechen
                                            </AlertDialogCancel>
                                            <AlertDialogAction
                                                onClick={handleRegenerateBackupCodes}
                                                disabled={regenerateCode.length < 6 || isRegenerating}
                                            >
                                                {isRegenerating && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                                Generieren
                                            </AlertDialogAction>
                                        </AlertDialogFooter>
                                    </AlertDialogContent>
                                </AlertDialog>
                            </div>
                        </div>

                        {status.backup_codes_remaining <= 2 && (
                            <Alert variant="destructive">
                                <AlertTriangle className="h-4 w-4" />
                                <AlertDescription>
                                    Sie haben nur noch {status.backup_codes_remaining} Backup-Codes.
                                    Generieren Sie neue Codes, um den Zugang zu Ihrem Konto zu sichern.
                                </AlertDescription>
                            </Alert>
                        )}
                    </div>

                    <Separator />

                    {/* Disable 2FA */}
                    <div className="space-y-4">
                        <h3 className="text-sm font-medium text-destructive flex items-center gap-2">
                            <ShieldOff className="w-4 h-4" />
                            2FA deaktivieren
                        </h3>

                        <Alert variant="destructive">
                            <AlertTriangle className="h-4 w-4" />
                            <AlertTitle>Warnung</AlertTitle>
                            <AlertDescription>
                                Das Deaktivieren von 2FA reduziert die Sicherheit Ihres Kontos erheblich.
                            </AlertDescription>
                        </Alert>

                        <AlertDialog>
                            <AlertDialogTrigger asChild>
                                <Button variant="destructive" className="w-full">
                                    <ShieldOff className="w-4 h-4 mr-2" />
                                    2FA deaktivieren
                                </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                                <AlertDialogHeader>
                                    <AlertDialogTitle>2FA wirklich deaktivieren?</AlertDialogTitle>
                                    <AlertDialogDescription className="space-y-4">
                                        <p>
                                            Geben Sie Ihren aktuellen 2FA-Code oder einen Backup-Code ein,
                                            um 2FA zu deaktivieren.
                                        </p>
                                        <Input
                                            type="text"
                                            inputMode="numeric"
                                            maxLength={12}
                                            placeholder="Code eingeben"
                                            value={disableCode}
                                            onChange={(e) => setDisableCode(e.target.value.replace(/[^0-9a-zA-Z-]/g, ''))}
                                            className="font-mono text-center text-lg tracking-widest"
                                        />
                                    </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                    <AlertDialogCancel onClick={() => setDisableCode('')}>
                                        Abbrechen
                                    </AlertDialogCancel>
                                    <AlertDialogAction
                                        onClick={handleDisable2FA}
                                        disabled={disableCode.length < 6 || isDisabling}
                                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                    >
                                        {isDisabling && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                        Deaktivieren
                                    </AlertDialogAction>
                                </AlertDialogFooter>
                            </AlertDialogContent>
                        </AlertDialog>
                    </div>
                </>
            )}
        </div>
    );
}
