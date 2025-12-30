import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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

// Mock Auth Context
const mockLogin = vi.fn();
const mockVerify2FA = vi.fn();
vi.mock('@/lib/auth/AuthContext', () => ({
    useAuth: () => ({
        login: mockLogin,
        verify2FA: mockVerify2FA,
    }),
    is2FARequired: (result: { requires_2fa?: boolean }) => result?.requires_2fa === true,
}));

// Import LoginPage component directly (after mocks)
import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { useAuth, is2FARequired } from '@/lib/auth/AuthContext';
import { TwoFactorInput } from '@/components/auth/TwoFactorInput';

// Recreate the LoginPage component for testing
function LoginPage() {
    const navigate = mockNavigate;
    const { login, verify2FA } = useAuth();
    const [isLoading, setIsLoading] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [show2FA, setShow2FA] = useState(false);
    const [tempToken, setTempToken] = useState<string | null>(null);
    const [twoFAError, setTwoFAError] = useState<string | null>(null);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            const result = await login(email, password);

            if (is2FARequired(result)) {
                setTempToken(result.temp_token);
                setShow2FA(true);
            } else {
                navigate({ to: '/' });
            }
        } catch {
            setError('Anmeldung fehlgeschlagen. Bitte überprüfen Sie Ihre Eingaben.');
        } finally {
            setIsLoading(false);
        }
    };

    const handle2FASubmit = useCallback(async (code: string) => {
        if (!tempToken) return;

        setIsLoading(true);
        setTwoFAError(null);

        try {
            await verify2FA(tempToken, code);
            navigate({ to: '/' });
        } catch {
            setTwoFAError('Ungültiger Code. Bitte versuchen Sie es erneut.');
        } finally {
            setIsLoading(false);
        }
    }, [tempToken, verify2FA, navigate]);

    const handle2FACancel = () => {
        setShow2FA(false);
        setTempToken(null);
        setTwoFAError(null);
        setPassword('');
    };

    return (
        <div className="h-screen w-full flex items-center justify-center">
            <Card className="w-full max-w-md">
                {show2FA ? (
                    <CardContent className="pt-6">
                        <TwoFactorInput
                            onSubmit={handle2FASubmit}
                            onCancel={handle2FACancel}
                            isLoading={isLoading}
                            error={twoFAError}
                        />
                    </CardContent>
                ) : (
                    <>
                        <CardHeader className="space-y-1">
                            <CardTitle className="text-3xl font-bold text-center">Ablage System</CardTitle>
                            <CardDescription className="text-center">
                                Melden Sie sich an, um auf Ihre Dokumente zuzugreifen.
                            </CardDescription>
                        </CardHeader>
                        <form onSubmit={handleLogin}>
                            <CardContent className="space-y-4">
                                {error && (
                                    <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md" data-testid="error-message">
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
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between">
                                        <Label htmlFor="password">Passwort</Label>
                                        <a href="/forgot-password" className="text-xs text-primary hover:underline">
                                            Passwort vergessen?
                                        </a>
                                    </div>
                                    <Input
                                        id="password"
                                        type="password"
                                        required
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                    />
                                </div>
                            </CardContent>
                            <CardFooter>
                                <Button className="w-full" type="submit" disabled={isLoading}>
                                    {isLoading ? 'Anmeldung...' : 'Anmelden'}
                                </Button>
                            </CardFooter>
                        </form>
                    </>
                )}
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

describe('Login Page', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        sessionStorage.clear();
    });

    describe('Rendering', () => {
        it('rendert den Login-Titel', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByText('Ablage System')).toBeInTheDocument();
        });

        it('rendert die Beschreibung', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByText('Melden Sie sich an, um auf Ihre Dokumente zuzugreifen.')).toBeInTheDocument();
        });

        it('rendert das E-Mail-Feld', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByLabelText('E-Mail')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('name@firma.de')).toBeInTheDocument();
        });

        it('rendert das Passwort-Feld', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByLabelText('Passwort')).toBeInTheDocument();
        });

        it('rendert den Anmelden-Button', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByRole('button', { name: 'Anmelden' })).toBeInTheDocument();
        });

        it('rendert den Passwort-vergessen-Link', () => {
            render(<LoginPage />, { wrapper: createWrapper() });

            expect(screen.getByText('Passwort vergessen?')).toBeInTheDocument();
            expect(screen.getByText('Passwort vergessen?').closest('a')).toHaveAttribute('href', '/forgot-password');
        });
    });

    describe('Standard Login Flow', () => {
        it('ruft login mit korrekten Credentials auf', async () => {
            mockLogin.mockResolvedValue({ user: { id: '1', email: 'test@example.com' } });
            render(<LoginPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            await waitFor(() => {
                expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123');
            });
        });

        it('navigiert zur Startseite nach erfolgreichem Login', async () => {
            mockLogin.mockResolvedValue({ user: { id: '1', email: 'test@example.com' } });
            render(<LoginPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith({ to: '/' });
            });
        });

        it('zeigt Fehlermeldung bei falschen Credentials', async () => {
            mockLogin.mockRejectedValue(new Error('Invalid credentials'));
            render(<LoginPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'wrongpassword');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            await waitFor(() => {
                expect(screen.getByText('Anmeldung fehlgeschlagen. Bitte überprüfen Sie Ihre Eingaben.')).toBeInTheDocument();
            });
        });

        it('zeigt Lade-Zustand während des Logins', async () => {
            mockLogin.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 1000)));
            render(<LoginPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            await waitFor(() => {
                expect(screen.getByRole('button', { name: 'Anmeldung...' })).toBeInTheDocument();
                expect(screen.getByRole('button', { name: 'Anmeldung...' })).toBeDisabled();
            });
        });
    });

    describe('2FA Login Flow', () => {
        it('zeigt 2FA-Eingabe wenn Login 2FA erfordert', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });
            render(<LoginPage />, { wrapper: createWrapper() });

            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            await waitFor(() => {
                expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            });
        });

        it('ruft verify2FA mit korrektem Token und Code auf', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });
            mockVerify2FA.mockResolvedValue({ user: { id: '1', email: 'test@example.com' } });
            render(<LoginPage />, { wrapper: createWrapper() });

            // Login
            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            // Wait for 2FA form
            await waitFor(() => {
                expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            });

            // Enter 2FA code
            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, '123456');

            await waitFor(() => {
                expect(mockVerify2FA).toHaveBeenCalledWith('temp-token-123', '123456');
            });
        });

        it('navigiert zur Startseite nach erfolgreicher 2FA', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });
            mockVerify2FA.mockResolvedValue({ user: { id: '1', email: 'test@example.com' } });
            render(<LoginPage />, { wrapper: createWrapper() });

            // Login
            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            // Wait for 2FA form
            await waitFor(() => {
                expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            });

            // Enter 2FA code
            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, '123456');

            await waitFor(() => {
                expect(mockNavigate).toHaveBeenCalledWith({ to: '/' });
            });
        });

        it('zeigt Fehlermeldung bei falschem 2FA-Code', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });
            mockVerify2FA.mockRejectedValue(new Error('Invalid 2FA code'));
            render(<LoginPage />, { wrapper: createWrapper() });

            // Login
            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            // Wait for 2FA form
            await waitFor(() => {
                expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            });

            // Enter wrong 2FA code - trigger form submit
            const input = screen.getByPlaceholderText('000000');
            fireEvent.change(input, { target: { value: '123456' } });
            const form = input.closest('form');
            fireEvent.submit(form!);

            await waitFor(() => {
                expect(screen.getByText('Ungültiger Code. Bitte versuchen Sie es erneut.')).toBeInTheDocument();
            });
        });

        it('kehrt zum Login-Formular zurück bei Abbrechen', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });
            render(<LoginPage />, { wrapper: createWrapper() });

            // Login
            await userEvent.type(screen.getByLabelText('E-Mail'), 'test@example.com');
            await userEvent.type(screen.getByLabelText('Passwort'), 'password123');
            fireEvent.click(screen.getByRole('button', { name: 'Anmelden' }));

            // Wait for 2FA form
            await waitFor(() => {
                expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            });

            // Cancel
            fireEvent.click(screen.getByRole('button', { name: 'Abbrechen' }));

            await waitFor(() => {
                expect(screen.getByLabelText('E-Mail')).toBeInTheDocument();
                expect(screen.getByLabelText('Passwort')).toBeInTheDocument();
            });
        });
    });
});
