/**
 * AuthContext Unit Tests
 *
 * Enterprise-Level Tests für den Auth Context Provider.
 * Testet Login-Flow, 2FA, Logout und State-Management.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth, is2FARequired } from '../AuthContext';

// Mock the auth service
const mockGetCurrentUser = vi.fn();
const mockLogin = vi.fn();
const mockVerify2FA = vi.fn();
const mockLogout = vi.fn();

vi.mock('@/lib/api/services/auth', () => ({
    authService: {
        getCurrentUser: () => mockGetCurrentUser(),
        login: (email: string, password: string) => mockLogin(email, password),
        verify2FA: (tempToken: string, code: string) => mockVerify2FA(tempToken, code),
        logout: () => mockLogout(),
    },
}));

// Test component to access auth context
function TestConsumer() {
    const auth = useAuth();
    return (
        <div>
            <div data-testid="loading">{auth.isLoading.toString()}</div>
            <div data-testid="authenticated">{auth.isAuthenticated.toString()}</div>
            <div data-testid="user">{auth.user ? JSON.stringify(auth.user) : 'null'}</div>
            <button data-testid="login-btn" onClick={() => auth.login('test@test.com', 'password')}>
                Login
            </button>
            <button data-testid="logout-btn" onClick={auth.logout}>
                Logout
            </button>
        </div>
    );
}

describe('AuthContext', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Default: no stored user
        mockGetCurrentUser.mockReturnValue(null);
    });

    describe('is2FARequired Type Guard', () => {
        it('gibt true zurück wenn requires_2fa true ist', () => {
            const result = { requires_2fa: true, temp_token: 'token-123' };
            expect(is2FARequired(result)).toBe(true);
        });

        it('gibt false zurück für normale AuthResponse', () => {
            const result = {
                user: { id: '1', email: 'test@test.com' },
                access_token: 'token',
                refresh_token: 'refresh',
                token_type: 'bearer',
            };
            expect(is2FARequired(result)).toBe(false);
        });

        it('gibt false zurück wenn requires_2fa false ist', () => {
            const result = { requires_2fa: false } as unknown;
            expect(is2FARequired(result as { requires_2fa: boolean })).toBe(false);
        });
    });

    describe('AuthProvider Initialization', () => {
        it('setzt isLoading auf false nach Initialisierung', async () => {
            // Mock synchrone Initialisierung
            mockGetCurrentUser.mockReturnValue(null);

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            // Nach synchroner Initialisierung sollte isLoading false sein
            await waitFor(() => {
                expect(screen.getByTestId('loading').textContent).toBe('false');
            });
        });

        it('lädt gespeicherten User beim Start', async () => {
            const storedUser = { id: '1', email: 'stored@test.com', role: 'admin' };
            mockGetCurrentUser.mockReturnValue(storedUser);

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('authenticated').textContent).toBe('true');
            });

            expect(JSON.parse(screen.getByTestId('user').textContent!)).toEqual(storedUser);
        });

        it('setzt isAuthenticated=false wenn kein User gespeichert', async () => {
            mockGetCurrentUser.mockReturnValue(null);

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('loading').textContent).toBe('false');
            });

            expect(screen.getByTestId('authenticated').textContent).toBe('false');
            expect(screen.getByTestId('user').textContent).toBe('null');
        });

        it('ruft logout bei Initialisierungsfehler auf', async () => {
            mockGetCurrentUser.mockImplementation(() => {
                throw new Error('Token expired');
            });

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('loading').textContent).toBe('false');
            });

            expect(mockLogout).toHaveBeenCalled();
        });
    });

    describe('Login Flow', () => {
        it('setzt User nach erfolgreichem Login', async () => {
            const user = { id: '1', email: 'new@test.com', role: 'user' };
            mockLogin.mockResolvedValue({
                user,
                access_token: 'token',
                refresh_token: 'refresh',
                token_type: 'bearer',
            });

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('loading').textContent).toBe('false');
            });

            await act(async () => {
                screen.getByTestId('login-btn').click();
            });

            await waitFor(() => {
                expect(screen.getByTestId('authenticated').textContent).toBe('true');
            });

            expect(mockLogin).toHaveBeenCalledWith('test@test.com', 'password');
        });

        it('setzt User NICHT wenn 2FA erforderlich', async () => {
            mockLogin.mockResolvedValue({
                requires_2fa: true,
                temp_token: 'temp-token-123',
            });

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('loading').textContent).toBe('false');
            });

            await act(async () => {
                screen.getByTestId('login-btn').click();
            });

            // User should still be null - waiting for 2FA
            expect(screen.getByTestId('authenticated').textContent).toBe('false');
            expect(screen.getByTestId('user').textContent).toBe('null');
        });
    });

    describe('2FA Verification', () => {
        it('setzt User nach erfolgreicher 2FA-Verifizierung', async () => {
            const user = { id: '1', email: 'test@test.com', role: 'admin' };
            mockVerify2FA.mockResolvedValue({
                user,
                access_token: 'token',
                refresh_token: 'refresh',
                token_type: 'bearer',
            });

            function TwoFATestConsumer() {
                const auth = useAuth();
                return (
                    <div>
                        <div data-testid="user">{auth.user ? 'logged-in' : 'not-logged-in'}</div>
                        <button
                            data-testid="verify-btn"
                            onClick={() => auth.verify2FA('temp-token', '123456')}
                        >
                            Verify 2FA
                        </button>
                    </div>
                );
            }

            render(
                <AuthProvider>
                    <TwoFATestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('user').textContent).toBe('not-logged-in');
            });

            await act(async () => {
                screen.getByTestId('verify-btn').click();
            });

            await waitFor(() => {
                expect(screen.getByTestId('user').textContent).toBe('logged-in');
            });

            expect(mockVerify2FA).toHaveBeenCalledWith('temp-token', '123456');
        });
    });

    describe('Logout Flow', () => {
        it('entfernt User bei Logout', async () => {
            const user = { id: '1', email: 'test@test.com', role: 'user' };
            mockGetCurrentUser.mockReturnValue(user);

            render(
                <AuthProvider>
                    <TestConsumer />
                </AuthProvider>
            );

            await waitFor(() => {
                expect(screen.getByTestId('authenticated').textContent).toBe('true');
            });

            await act(async () => {
                screen.getByTestId('logout-btn').click();
            });

            expect(screen.getByTestId('authenticated').textContent).toBe('false');
            expect(screen.getByTestId('user').textContent).toBe('null');
            expect(mockLogout).toHaveBeenCalled();
        });
    });

    describe('useAuth Hook', () => {
        it('wirft Fehler wenn außerhalb von AuthProvider verwendet', () => {
            const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

            expect(() => {
                render(<TestConsumer />);
            }).toThrow('useAuth must be used within an AuthProvider');

            consoleError.mockRestore();
        });
    });
});
