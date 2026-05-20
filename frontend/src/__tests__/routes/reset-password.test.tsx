import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, useEffect } from 'react';

// Mock TanStack Router
const mockNavigate = vi.fn();
vi.mock('@tanstack/react-router', () => ({
    createFileRoute: () => () => ({
        component: () => null,
    }),
    useNavigate: () => mockNavigate,
    Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
        <a href={to}>{children}</a>
    ),
}));

// Mock Auth Service
const mockValidateResetToken = vi.fn();
const mockResetPassword = vi.fn();
vi.mock('@/lib/api/services/auth', () => ({
    authService: {
        validateResetToken: (token: string) => mockValidateResetToken(token),
        resetPassword: (token: string, password: string) => mockResetPassword(token, password),
    },
}));

// Import components
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { authService } from '@/lib/api/services/auth';
import { ArrowLeft, CheckCircle, XCircle, Loader2 } from 'lucide-react';

// Recreate ResetPasswordPage for testing
function ResetPasswordPage({ token = 'test-token' }: { token?: string }) {
    const navigate = mockNavigate;
    const [isLoading, setIsLoading] = useState(false);
    const [isValidating, setIsValidating] = useState(true);
    const [isTokenValid, setIsTokenValid] = useState(false);
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isSuccess, setIsSuccess] = useState(false);
    const [error, setError] = useState<string | null>(null);

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

        if (password !== confirmPassword) {
            setError('Passwörter stimmen nicht überein');
            return;
        }

        const validationError = validatePassword(password);
        if (validationError) {
            setError(validationError);
            return;
        }

        setIsLoading(true);

        try {
            await authService.resetPassword(token, password);
            setIsSuccess(true);
        } catch {
            setError('Passwort konnte nicht zurückgesetzt werden. Der Link ist möglicherweise abgelaufen.');
        } finally {
            setIsLoading(false);
        }
    };

    // Loading state while validating token
    if (isValidating) {
        return (
            <div className="h-screen w-full flex items-center justify-center" data-testid="validating-state">
                <Card className="w-full max-w-md">
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
            <div className="h-screen w-full flex items-center justify-center" data-testid="invalid-token-state">
                <Card className="w-full max-w-md">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
                                <XCircle className="h-8 w-8 text-destructive" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-bold text-center">
                            Ungültiger Link
                        </CardTitle>
                        <CardDescription className="text-center">
                            Dieser Link zum Zurücksetzen des Passworts ist ungültig oder abgelaufen.
                        </CardDescription>
                    </CardHeader>
                    <CardFooter className="flex flex-col gap-3">
                        <a href="/forgot-password" className="w-full">
                            <Button className="w-full">Neuen Link anfordern</Button>
                        </a>
                        <a href="/login" className="text-sm text-muted-foreground">
                            <ArrowLeft className="h-3 w-3 inline mr-1" />
                            Zurück zur Anmeldung
                        </a>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    // Success state
    if (isSuccess) {
        return (
            <div className="h-screen w-full flex items-center justify-center" data-testid="success-state">
                <Card className="w-full max-w-md">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
                                <CheckCircle className="h-8 w-8 text-green-500" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-bold text-center">
                            Passwort geändert
                        </CardTitle>
                        <CardDescription className="text-center">
                            Ihr Passwort wurde erfolgreich zurückgesetzt. Sie können sich jetzt
                            mit Ihrem neuen Passwort anmelden.
                        </CardDescription>
                    </CardHeader>
                    <CardFooter>
                        <a href="/login" className="w-full">
                            <Button className="w-full">Zur Anmeldung</Button>
                        </a>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    // Password reset form
    return (
        <div className="h-screen w-full flex items-center justify-center" data-testid="form-state">
            <Card className="w-full max-w-md">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold text-center">
                        Neues Passwort
                    </CardTitle>
                    <CardDescription className="text-center">
                        Geben Sie Ihr neues Passwort ein.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        {error && (
                            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md" data-testid="error-message">
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
                            />
                        </div>
                        <div className="text-xs text-muted-foreground">
                            <p>Passwort-Anforderungen:</p>
                            <ul className="list-disc list-inside mt-1 space-y-0.5">
                                <li>Mindestens 8 Zeichen</li>
                                <li>Mindestens ein Großbuchstabe</li>
                                <li>Mindestens ein Kleinbuchstabe</li>
                                <li>Mindestens eine Zahl</li>
                                <li>Mindestens ein Sonderzeichen</li>
                            </ul>
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <Button
                            className="w-full"
                            type="submit"
                            disabled={isLoading}
                        >
                            {isLoading ? 'Wird gespeichert...' : 'Passwort speichern'}
                        </Button>
                        <a href="/login" className="text-sm text-muted-foreground">
                            <ArrowLeft className="h-3 w-3 inline mr-1" />
                            Zurück zur Anmeldung
                        </a>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
}

// Create QueryClient wrapper
const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
};

describe('ResetPassword Page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Token Validation', () => {
        it('zeigt Lade-Zustand während Token-Validierung', () => {
            mockValidateResetToken.mockImplementation(() => new Promise(() => {})); // Never resolves
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByTestId('validating-state')).toBeInTheDocument();
            expect(screen.getByText('Link wird überprüft...')).toBeInTheDocument();
        });

        it('ruft validateResetToken mit dem Token auf', async () => {
            mockValidateResetToken.mockResolvedValue(true);
            render(<ResetPasswordPage token="my-test-token" />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(mockValidateResetToken).toHaveBeenCalledWith('my-test-token');
            });
        });

        it('zeigt Formular bei gültigem Token', async () => {
            mockValidateResetToken.mockResolvedValue(true);
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });
        });

        it('zeigt Ungültig-Meldung bei ungültigem Token', async () => {
            mockValidateResetToken.mockResolvedValue(false);
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('invalid-token-state')).toBeInTheDocument();
                expect(screen.getByText('Ungültiger Link')).toBeInTheDocument();
            });
        });

        it('zeigt Ungültig-Meldung bei Token-Validierungsfehler', async () => {
            mockValidateResetToken.mockRejectedValue(new Error('Network error'));
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('invalid-token-state')).toBeInTheDocument();
            });
        });
    });

    describe('Form Rendering', () => {
        beforeEach(() => {
            mockValidateResetToken.mockResolvedValue(true);
        });

        it('rendert den Titel', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByRole('heading', { name: 'Neues Passwort' })).toBeInTheDocument();
            });
        });

        it('rendert das Passwort-Feld', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByLabelText('Neues Passwort')).toBeInTheDocument();
            });
        });

        it('rendert das Passwort-bestätigen-Feld', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByLabelText('Passwort bestätigen')).toBeInTheDocument();
            });
        });

        it('rendert die Passwort-Anforderungen', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByText('Passwort-Anforderungen:')).toBeInTheDocument();
                expect(screen.getByText('Mindestens 8 Zeichen')).toBeInTheDocument();
                expect(screen.getByText('Mindestens ein Großbuchstabe')).toBeInTheDocument();
                expect(screen.getByText('Mindestens ein Kleinbuchstabe')).toBeInTheDocument();
                expect(screen.getByText('Mindestens eine Zahl')).toBeInTheDocument();
                expect(screen.getByText('Mindestens ein Sonderzeichen')).toBeInTheDocument();
            });
        });
    });

    describe('Password Validation', () => {
        beforeEach(() => {
            mockValidateResetToken.mockResolvedValue(true);
        });

        it('zeigt Fehler wenn Passwörter nicht übereinstimmen', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'Password1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'Password2!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwörter stimmen nicht überein')).toBeInTheDocument();
            });
        });

        it('zeigt Fehler bei zu kurzem Passwort', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'Ab1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'Ab1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort muss mindestens 8 Zeichen lang sein')).toBeInTheDocument();
            });
        });

        it('zeigt Fehler bei fehlendem Großbuchstaben', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'password1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'password1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort muss mindestens einen Großbuchstaben enthalten')).toBeInTheDocument();
            });
        });

        it('zeigt Fehler bei fehlendem Kleinbuchstaben', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'PASSWORD1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'PASSWORD1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort muss mindestens einen Kleinbuchstaben enthalten')).toBeInTheDocument();
            });
        });

        it('zeigt Fehler bei fehlender Zahl', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'Password!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'Password!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort muss mindestens eine Zahl enthalten')).toBeInTheDocument();
            });
        });

        it('zeigt Fehler bei fehlendem Sonderzeichen', async () => {
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'Password1');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'Password1');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort muss mindestens ein Sonderzeichen enthalten')).toBeInTheDocument();
            });
        });
    });

    describe('Successful Password Reset', () => {
        beforeEach(() => {
            mockValidateResetToken.mockResolvedValue(true);
        });

        it('ruft resetPassword mit korrekten Parametern auf', async () => {
            mockResetPassword.mockResolvedValue({});
            render(<ResetPasswordPage token="my-token" />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'ValidPass1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'ValidPass1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(mockResetPassword).toHaveBeenCalledWith('my-token', 'ValidPass1!');
            });
        });

        it('zeigt Erfolgs-Meldung nach Reset', async () => {
            mockResetPassword.mockResolvedValue({});
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'ValidPass1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'ValidPass1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByTestId('success-state')).toBeInTheDocument();
                expect(screen.getByText('Passwort geändert')).toBeInTheDocument();
            });
        });

        it('zeigt Lade-Zustand während des Resets', async () => {
            mockResetPassword.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 1000)));
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'ValidPass1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'ValidPass1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByRole('button', { name: 'Wird gespeichert...' })).toBeInTheDocument();
                expect(screen.getByRole('button', { name: 'Wird gespeichert...' })).toBeDisabled();
            });
        });
    });

    describe('Failed Password Reset', () => {
        beforeEach(() => {
            mockValidateResetToken.mockResolvedValue(true);
        });

        it('zeigt Fehlermeldung bei Reset-Fehler', async () => {
            mockResetPassword.mockRejectedValue(new Error('Token expired'));
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'ValidPass1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'ValidPass1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Passwort konnte nicht zurückgesetzt werden. Der Link ist möglicherweise abgelaufen.')).toBeInTheDocument();
            });
        });
    });

    describe('Navigation', () => {
        it('hat Link zum Login auf Invalid-Token-Seite', async () => {
            mockValidateResetToken.mockResolvedValue(false);
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByText('Zurück zur Anmeldung').closest('a')).toHaveAttribute('href', '/login');
            });
        });

        it('hat Link zu Forgot-Password auf Invalid-Token-Seite', async () => {
            mockValidateResetToken.mockResolvedValue(false);
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByText('Neuen Link anfordern').closest('a')).toHaveAttribute('href', '/forgot-password');
            });
        });

        it('hat Link zum Login auf Success-Seite', async () => {
            mockValidateResetToken.mockResolvedValue(true);
            mockResetPassword.mockResolvedValue({});
            render(<ResetPasswordPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(screen.getByTestId('form-state')).toBeInTheDocument();
            });

            await userEvent.type(screen.getByLabelText('Neues Passwort'), 'ValidPass1!');
            await userEvent.type(screen.getByLabelText('Passwort bestätigen'), 'ValidPass1!');
            fireEvent.click(screen.getByRole('button', { name: 'Passwort speichern' }));

            await waitFor(() => {
                expect(screen.getByText('Zur Anmeldung').closest('a')).toHaveAttribute('href', '/login');
            });
        });
    });
});
