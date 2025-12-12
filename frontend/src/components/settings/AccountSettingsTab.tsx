/**
 * Konto-Einstellungen Tab.
 *
 * Enthält:
 * - Benutzerinformationen anzeigen
 * - Passwort ändern
 * - Abmelden
 * - Konto löschen (GDPR Art. 17)
 */

import { useState } from 'react';
import { Loader2, LogOut, Trash2, AlertTriangle, User, Mail, Shield, Key } from 'lucide-react';
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
import { useAuth } from '@/lib/auth/AuthContext';
import { apiClient } from '@/lib/api/client';
import { useToast } from '@/components/ui/use-toast';

interface AccountSettingsTabProps {
    onClose: () => void;
}

export function AccountSettingsTab({ onClose }: AccountSettingsTabProps) {
    const { user, logout } = useAuth();
    const { toast } = useToast();

    // Password change state
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isChangingPassword, setIsChangingPassword] = useState(false);
    const [passwordError, setPasswordError] = useState<string | null>(null);

    // Account deletion state
    const [deleteConfirmText, setDeleteConfirmText] = useState('');
    const [isDeleting, setIsDeleting] = useState(false);

    const handlePasswordChange = async () => {
        setPasswordError(null);

        // Validation
        if (!currentPassword || !newPassword || !confirmPassword) {
            setPasswordError('Bitte füllen Sie alle Felder aus.');
            return;
        }
        if (newPassword.length < 8) {
            setPasswordError('Das neue Passwort muss mindestens 8 Zeichen haben.');
            return;
        }
        if (newPassword !== confirmPassword) {
            setPasswordError('Die Passwörter stimmen nicht überein.');
            return;
        }
        if (!/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
            setPasswordError('Das Passwort muss Gross-/Kleinbuchstaben und Zahlen enthalten.');
            return;
        }

        setIsChangingPassword(true);
        try {
            await apiClient.post('/auth/change-password', {
                current_password: currentPassword,
                new_password: newPassword,
            });

            toast({
                title: 'Passwort geändert',
                description: 'Ihr Passwort wurde erfolgreich aktualisiert.',
            });

            // Clear form
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            setPasswordError(errorMessage || 'Passwort konnte nicht geändert werden.');
            toast({
                title: 'Fehler',
                description: 'Passwort konnte nicht geändert werden.',
                variant: 'destructive',
            });
        } finally {
            setIsChangingPassword(false);
        }
    };

    const handleLogout = () => {
        onClose();
        logout();
    };

    const handleDeleteAccount = async () => {
        if (deleteConfirmText !== 'LÖSCHEN') {
            toast({
                title: 'Bestätigung erforderlich',
                description: 'Bitte geben Sie "LÖSCHEN" ein um fortzufahren.',
                variant: 'destructive',
            });
            return;
        }

        setIsDeleting(true);
        try {
            await apiClient.post('/users/me/gdpr/request-deletion', {
                reason: 'Benutzer-angeforderte Kontolöschung',
                confirm: true,
            });

            toast({
                title: 'Löschantrag gesendet',
                description: 'Ihr Konto wird in 30 Tagen gelöscht. Sie erhalten eine Bestätigung per E-Mail.',
            });

            setDeleteConfirmText('');
            onClose();
        } catch (error) {
            console.error('Fehler beim Löschen:', error);
            toast({
                title: 'Fehler',
                description: 'Löschantrag konnte nicht gesendet werden.',
                variant: 'destructive',
            });
        } finally {
            setIsDeleting(false);
        }
    };

    const getRoleDisplay = () => {
        if (user?.is_superuser) return 'Administrator';
        if (user?.role === 'admin') return 'Administrator';
        if (user?.role === 'editor') return 'Editor';
        return 'Benutzer';
    };

    return (
        <div className="space-y-6">
            {/* User Info Section */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium flex items-center gap-2">
                    <User className="w-4 h-4" />
                    Kontoinformationen
                </h3>

                <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-muted/50">
                    <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Benutzername</Label>
                        <p className="font-medium">{user?.username || '-'}</p>
                    </div>
                    <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Vollständiger Name</Label>
                        <p className="font-medium">{user?.full_name || '-'}</p>
                    </div>
                    <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1">
                            <Mail className="w-3 h-3" />
                            E-Mail
                        </Label>
                        <p className="font-medium">{user?.email || '-'}</p>
                    </div>
                    <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground flex items-center gap-1">
                            <Shield className="w-3 h-3" />
                            Rolle
                        </Label>
                        <p className="font-medium">{getRoleDisplay()}</p>
                    </div>
                </div>
            </div>

            <Separator />

            {/* Password Change Section */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium flex items-center gap-2">
                    <Key className="w-4 h-4" />
                    Passwort ändern
                </h3>

                {passwordError && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>{passwordError}</AlertDescription>
                    </Alert>
                )}

                <div className="space-y-3">
                    <div className="space-y-2">
                        <Label htmlFor="current-password">Aktuelles Passwort</Label>
                        <Input
                            id="current-password"
                            type="password"
                            value={currentPassword}
                            onChange={(e) => setCurrentPassword(e.target.value)}
                            placeholder="Ihr aktuelles Passwort"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-2">
                            <Label htmlFor="new-password">Neues Passwort</Label>
                            <Input
                                id="new-password"
                                type="password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                placeholder="Min. 8 Zeichen"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="confirm-password">Passwort bestätigen</Label>
                            <Input
                                id="confirm-password"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="Passwort wiederholen"
                            />
                        </div>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        Das Passwort muss mindestens 8 Zeichen haben und Gross-/Kleinbuchstaben sowie Zahlen enthalten.
                    </p>
                    <Button
                        onClick={handlePasswordChange}
                        disabled={isChangingPassword || !currentPassword || !newPassword || !confirmPassword}
                    >
                        {isChangingPassword && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                        Passwort ändern
                    </Button>
                </div>
            </div>

            <Separator />

            {/* Session Section */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium flex items-center gap-2">
                    <LogOut className="w-4 h-4" />
                    Sitzung
                </h3>

                <div className="flex items-center justify-between p-4 rounded-lg border">
                    <div>
                        <p className="font-medium">Abmelden</p>
                        <p className="text-xs text-muted-foreground">
                            Beendet Ihre aktuelle Sitzung und leitet Sie zur Login-Seite weiter.
                        </p>
                    </div>
                    <Button variant="outline" onClick={handleLogout}>
                        <LogOut className="w-4 h-4 mr-2" />
                        Abmelden
                    </Button>
                </div>
            </div>

            <Separator />

            {/* Danger Zone - Account Deletion */}
            <div className="space-y-4">
                <h3 className="text-sm font-medium text-destructive flex items-center gap-2">
                    <Trash2 className="w-4 h-4" />
                    Gefahrenzone
                </h3>

                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Konto löschen</AlertTitle>
                    <AlertDescription>
                        Wenn Sie Ihr Konto löschen, werden alle Ihre Daten nach 30 Tagen unwiderruflich entfernt.
                        Diese Aktion kann innerhalb der 30-Tage-Frist abgebrochen werden.
                    </AlertDescription>
                </Alert>

                <AlertDialog>
                    <AlertDialogTrigger asChild>
                        <Button variant="destructive" className="w-full">
                            <Trash2 className="w-4 h-4 mr-2" />
                            Konto löschen anfordern
                        </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>Sind Sie sicher?</AlertDialogTitle>
                            <AlertDialogDescription className="space-y-4">
                                <p>
                                    Diese Aktion kann nicht rückgängig gemacht werden. Ihr Konto und alle
                                    zugehörigen Daten werden nach 30 Tagen dauerhaft gelöscht.
                                </p>
                                <p>
                                    Geben Sie <strong>LÖSCHEN</strong> ein, um fortzufahren:
                                </p>
                                <Input
                                    value={deleteConfirmText}
                                    onChange={(e) => setDeleteConfirmText(e.target.value)}
                                    placeholder="LÖSCHEN"
                                    className="mt-2"
                                />
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel onClick={() => setDeleteConfirmText('')}>
                                Abbrechen
                            </AlertDialogCancel>
                            <AlertDialogAction
                                onClick={handleDeleteAccount}
                                disabled={deleteConfirmText !== 'LÖSCHEN' || isDeleting}
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                                {isDeleting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                Konto löschen
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
            </div>
        </div>
    );
}
