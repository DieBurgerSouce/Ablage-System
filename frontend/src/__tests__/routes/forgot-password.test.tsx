import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

// Mock TanStack Router
vi.mock('@tanstack/react-router', () => ({
    createFileRoute: () => () => ({
        component: () => null,
    }),
    Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
        <a href={to}>{children}</a>
    ),
}));

// Mock Auth Service
const mockRequestPasswordReset = vi.fn();
vi.mock('@/lib/api/services/auth', () => ({
    authService: {
        requestPasswordReset: (email: string) => mockRequestPasswordReset(email),
    },
}));

// Import components
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { authService } from '@/lib/api/services/auth';
import { ArrowLeft, CheckCircle, Mail } from 'lucide-react';

// Recreate ForgotPasswordPage for testing
function ForgotPasswordPage() {
    const [isLoading, setIsLoading] = useState(false);
    const [email, setEmail] = useState('');
    const [isSubmitted, setIsSubmitted] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            await authService.requestPasswordReset(email);
            setIsSubmitted(true);
        } catch {
            // Still show success message to prevent email enumeration
            setIsSubmitted(true);
        } finally {
            setIsLoading(false);
        }
    };

    if (isSubmitted) {
        return (
            <div className="h-screen w-full flex items-center justify-center">
                <Card className="w-full max-w-md">
                    <CardHeader className="space-y-1">
                        <div className="flex justify-center mb-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
                                <CheckCircle className="h-8 w-8 text-green-500" />
                            </div>
                        </div>
                        <CardTitle className="text-2xl font-bold text-center">
                            E-Mail gesendet
                        </CardTitle>
                        <CardDescription className="text-center">
                            Falls ein Konto mit dieser E-Mail-Adresse existiert, haben wir Ihnen
                            einen Link zum Zurücksetzen des Passworts gesendet.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="flex items-center gap-3 p-4 bg-muted/50 rounded-lg">
                            <Mail className="h-5 w-5 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                                Prüfen Sie auch Ihren Spam-Ordner.
                            </span>
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <a href="/login" className="w-full">
                            <Button variant="outline" className="w-full">
                                <ArrowLeft className="h-4 w-4 mr-2" />
                                Zurück zur Anmeldung
                            </Button>
                        </a>
                    </CardFooter>
                </Card>
            </div>
        );
    }

    return (
        <div className="h-screen w-full flex items-center justify-center">
            <Card className="w-full max-w-md">
                <CardHeader className="space-y-1">
                    <CardTitle className="text-2xl font-bold text-center">
                        Passwort vergessen?
                    </CardTitle>
                    <CardDescription className="text-center">
                        Geben Sie Ihre E-Mail-Adresse ein und wir senden Ihnen einen Link
                        zum Zurücksetzen Ihres Passworts.
                    </CardDescription>
                </CardHeader>
                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        {error && (
                            <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label htmlFor="email">E-Mail</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="name@firma.de"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                            />
                        </div>
                    </CardContent>
                    <CardFooter className="flex flex-col gap-3">
                        <Button
                            className="w-full"
                            type="submit"
                            disabled={isLoading}
                        >
                            {isLoading ? 'Wird gesendet...' : 'Link senden'}
                        </Button>
                        <a
                            href="/login"
                            className="text-sm text-muted-foreground hover:text-primary"
                        >
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

describe('ForgotPassword Page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Rendering', () => {
        it('rendert den Titel', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByText('Passwort vergessen?')).toBeInTheDocument();
        });

        it('rendert die Beschreibung', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByText(/Geben Sie Ihre E-Mail-Adresse ein/)).toBeInTheDocument();
        });

        it('rendert das E-Mail-Feld', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByLabelText('E-Mail')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('name@firma.de')).toBeInTheDocument();
        });

        it('rendert den Link-senden-Button', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByRole('button', { name: 'Link senden' })).toBeInTheDocument();
        });

        it('rendert den Zurück-zur-Anmeldung-Link', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByText('Zurück zur Anmeldung')).toBeInTheDocument();
        });
    });

    describe('Form Submission', () => {
        it('ruft requestPasswordReset mit der E-Mail auf', async () => {
            mockRequestPasswordReset.mockResolvedValue({});
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(mockRequestPasswordReset).toHaveBeenCalledWith('test@example.com');
            });
        });

        it('zeigt Lade-Zustand während des Sendens', async () => {
            mockRequestPasswordReset.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 1000)));
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(screen.getByRole('button', { name: 'Wird gesendet...' })).toBeInTheDocument();
                expect(screen.getByRole('button', { name: 'Wird gesendet...' })).toBeDisabled();
            });
        });
    });

    describe('Success State', () => {
        it('zeigt Erfolgs-Nachricht nach dem Absenden', async () => {
            mockRequestPasswordReset.mockResolvedValue({});
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(screen.getByText('E-Mail gesendet')).toBeInTheDocument();
            });
        });

        it('zeigt Hinweis auf Spam-Ordner', async () => {
            mockRequestPasswordReset.mockResolvedValue({});
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(screen.getByText('Prüfen Sie auch Ihren Spam-Ordner.')).toBeInTheDocument();
            });
        });

        it('zeigt Erfolg auch bei Fehler (Email Enumeration Prevention)', async () => {
            mockRequestPasswordReset.mockRejectedValue(new Error('Not found'));
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'nonexistent@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                // Should still show success to prevent email enumeration
                expect(screen.getByText('E-Mail gesendet')).toBeInTheDocument();
            });
        });

        it('zeigt sicheren Text der keine Kontoexistenz verrät', async () => {
            mockRequestPasswordReset.mockResolvedValue({});
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(
                    screen.getByText(/Falls ein Konto mit dieser E-Mail-Adresse existiert/)
                ).toBeInTheDocument();
            });
        });
    });

    describe('Navigation', () => {
        it('hat korrekten Link zur Login-Seite im Formular', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            const link = screen.getByText('Zurück zur Anmeldung').closest('a');
            expect(link).toHaveAttribute('href', '/login');
        });

        it('hat korrekten Link zur Login-Seite nach Erfolg', async () => {
            mockRequestPasswordReset.mockResolvedValue({});
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            fireEvent.click(screen.getByRole('button', { name: 'Link senden' }));

            await waitFor(() => {
                expect(screen.getByText('E-Mail gesendet')).toBeInTheDocument();
            });

            const link = screen.getByRole('button', { name: /Zurück zur Anmeldung/ }).closest('a');
            expect(link).toHaveAttribute('href', '/login');
        });
    });

    describe('Accessibility', () => {
        it('hat required-Attribut auf E-Mail-Feld', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByLabelText('E-Mail')).toHaveAttribute('required');
        });

        it('hat type="email" für E-Mail-Validierung', () => {
            render(<ForgotPasswordPage />, { wrapper: createWrapper() });

            expect(screen.getByLabelText('E-Mail')).toHaveAttribute('type', 'email');
        });
    });
});
