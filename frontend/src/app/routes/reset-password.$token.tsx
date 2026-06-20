import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import { logger } from '@/lib/logger';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { authService } from '@/lib/api/services/auth';
import { ArrowLeft, CheckCircle, XCircle, Loader2 } from 'lucide-react';

export const Route = createFileRoute('/reset-password/$token')({
    component: ResetPasswordPage,
});

function ResetPasswordPage() {
    const { token } = Route.useParams();
    void useNavigate();
    const [isLoading, setIsLoading] = useState(false);
    const [isValidating, setIsValidating] = useState(true);
    const [isTokenValid, setIsTokenValid] = useState(false);
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isSuccess, setIsSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Validate token on mount
    useEffect(() => {
        const validateToken = async () => {
            try {
                const valid = await authService.validateResetToken(token);
                setIsTokenValid(valid);
            } catch {
                setIsTokenValid(false);
            } finally {
                setIsValidating(false);
            }
        };

        validateToken();
    }, [token]);

    const validatePassword = (pwd: string): string | null => {
        if (pwd.length < 8) {
            return 'Passwort muss mindestens 8 Zeichen lang sein';
        }
        if (!/[A-Z]/.test(pwd)) {
            return 'Passwort muss mindestens einen Großbuchstaben enthalten';
        }
        if (!/[a-z]/.test(pwd)) {
            return 'Passwort muss mindestens einen Kleinbuchstaben enthalten';
        }
        if (!/[0-9]/.test(pwd)) {
            return 'Passwort muss mindestens eine Zahl enthalten';
        }
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(pwd)) {
            return 'Passwort muss mindestens ein Sonderzeichen enthalten';
        }
        return null;
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        // Validate passwords match
        if (password !== confirmPassword) {
            setError('Passwörter stimmen nicht überein');
            return;
        }

        // Validate password requirements
        const validationError = validatePassword(password);
        if (validationError) {
            setError(validationError);
            return;
        }

        setIsLoading(true);

        try {
            await authService.resetPassword(token, password);
            setIsSuccess(true);
        } catch (err) {
            logger.error('Passwort-Zurücksetzen fehlgeschlagen', err);
            setError('Passwort konnte nicht zurückgesetzt werden. Der Link ist möglicherweise abgelaufen.');
        } finally {
            setIsLoading(false);
        }
    };

    // Loading state while validating token
    if (isValidating) {
        return (
            <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
                <div className="noise-overlay absolute inset-0" />

                <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                    <CardContent className="flex flex-col items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                        <p className="text-muted-foreground">Link wird überprüft...</p>
                    </CardContent>
                </Card>
            </div>
        );
    }

    // Invalid token state
    if (!isTokenValid) {
        return (
            <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
                <div className="noise-overlay absolute inset-0" />

                <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
                                <XCircle className="h-8 w-8 text-destructive" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-display font-bold text-center tracking-tight">
                            Ungültiger Link
                        </CardTitle>
                        <CardDescription className="text-center text-muted-foreground/80">
                            Dieser Link zum Zurücksetzen des Passworts ist ungültig oder abgelaufen.
                        </CardDescription>
                    </CardHeader>
                    <CardFooter className="flex flex-col gap-3">
                        <Link to="/forgot-password" className="w-full">
                            <Button className="w-full">Neuen Link anfordern</Button>
                        </Link>
                        <Link
                            to="/login"
                            className="text-sm text-muted-foreground hover:text-primary transition-colors"
                        >
                            <ArrowLeft className="h-3 w-3 inline mr-1" />
                            Zurück zur Anmeldung
                        </Link>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    // Success state
    if (isSuccess) {
        return (
            <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
                <div className="noise-overlay absolute inset-0" />

                <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
                                <CheckCircle className="h-8 w-8 text-green-500" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-display font-bold text-center tracking-tight">
                            Passwort geändert
                        </CardTitle>
                        <CardDescription className="text-center text-muted-foreground/80">
                            Ihr Passwort wurde erfolgreich zurückgesetzt. Sie können sich jetzt
                            mit Ihrem neuen Passwort anmelden.
                        </CardDescription>
                    </CardHeader>
                    <CardFooter>
                        <Link to="/login" className="w-full">
                            <Button className="w-full">Zur Anmeldung</Button>
                        </Link>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    // Password reset form
    return (
        <div className="h-screen w-full flex items-center justify-center bg-background relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent/5" />
            <div className="noise-overlay absolute inset-0" />

            <Card className="w-full max-w-md glass-card relative z-10 border-white/10 shadow-2xl backdrop-blur-xl">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-display font-bold text-center tracking-tight">
                        Neues Passwort
                    </CardTitle>
                    <CardDescription className="text-center text-muted-foreground/80">
                        Geben Sie Ihr neues Passwort ein.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        {error && (
                            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md border border-destructive/20">
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label htmlFor="password">Neues Passwort</Label>
                            <Input
                                id="password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="bg-background/50 border-white/10 focus:border-primary/50 transition-colors"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="confirmPassword">Passwort bestätigen</Label>
                            <Input
                                id="confirmPassword"
                                type="password"
                                required
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="bg-background/50 border-white/10 focus:border-primary/50 transition-colors"
                            />
                        </div>
                        <div className="text-xs text-muted-foreground">
                            <p>Passwort-Anforderungen:</p>
                            <ul className="list-disc list-inside mt-1 space-y-0.5">
                                <li>Mindestens 8 Zeichen</li>
                                <li>Mindestens ein Grossbuchstabe</li>
                                <li>Mindestens ein Kleinbuchstabe</li>
                                <li>Mindestens eine Zahl</li>
                                <li>Mindestens ein Sonderzeichen</li>
                            </ul>
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <Button
                            className="w-full font-medium shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-all"
                            type="submit"
                            disabled={isLoading}
                        >
                            {isLoading ? 'Wird gespeichert...' : 'Passwort speichern'}
                        </Button>
                        <Link
                            to="/login"
                            className="text-sm text-muted-foreground hover:text-primary transition-colors"
                        >
                            <ArrowLeft className="h-3 w-3 inline mr-1" />
                            Zurück zur Anmeldung
                        </Link>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
}
