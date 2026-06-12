/**
 * SecuritySettingsTab Unit Tests
 *
 * Enterprise-Level Tests für die Sicherheits-Einstellungen.
 * Testet 2FA Setup, Status, Disable und Backup-Code Regeneration.
 */

import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SecuritySettingsTab } from '../SecuritySettingsTab';

// ActiveSessionsTab nutzt TanStack Query (eigener QueryClient-Kontext) und hat
// eigene Tests — fuer den 2FA-Unit-Test als Stub mocken, sonst crasht der Baum
// mit 'No QueryClient set'.
vi.mock('../ActiveSessionsTab', () => ({
    ActiveSessionsTab: () => null,
}));

// Mock the auth service
const mockGet2FAStatus = vi.fn();
const mockSetup2FA = vi.fn();
const mockVerify2FASetup = vi.fn();
const mockDisable2FA = vi.fn();
const mockRegenerateBackupCodes = vi.fn();

vi.mock('@/lib/api/services/auth', () => ({
    authService: {
        get2FAStatus: () => mockGet2FAStatus(),
        setup2FA: () => mockSetup2FA(),
        verify2FASetup: (code: string) => mockVerify2FASetup(code),
        disable2FA: (code: string) => mockDisable2FA(code),
        regenerateBackupCodes: (code: string) => mockRegenerateBackupCodes(code),
    },
}));

// Mock useToast
const mockToast = vi.fn();
vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({
        toast: mockToast,
    }),
}));

// Mock clipboard API
const mockWriteText = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
    value: {
        writeText: mockWriteText,
    },
    writable: true,
    configurable: true,
});

describe('SecuritySettingsTab', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Default: 2FA not enabled
        mockGet2FAStatus.mockResolvedValue({
            enabled: false,
            available: true,
            backup_codes_remaining: 0,
        });
    });

    // ==================== Loading State ====================

    describe('Loading State', () => {
        it('zeigt Ladeindikator während Status geladen wird', () => {
            // Mock that doesn't resolve immediately
            mockGet2FAStatus.mockImplementation(() => new Promise(() => {}));

            render(<SecuritySettingsTab />);

            // The spinner has class animate-spin
            const spinner = document.querySelector('.animate-spin');
            expect(spinner).toBeInTheDocument();
        });
    });

    // ==================== 2FA Disabled State ====================

    describe('2FA deaktiviert', () => {
        beforeEach(() => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: false,
                available: true,
                backup_codes_remaining: 0,
            });
        });

        it('zeigt "2FA ist deaktiviert" Status', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByText('2FA ist deaktiviert')).toBeInTheDocument();
            });
        });

        it('zeigt Aktivieren-Button', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });
        });

        it('startet Setup bei Klick auf Aktivieren', async () => {
            const setupData = {
                qr_code: 'data:image/png;base64,test',
                provisioning_uri: 'otpauth://totp/Test?secret=TESTSECRET&issuer=Test',
                backup_codes: ['CODE1', 'CODE2', 'CODE3', 'CODE4', 'CODE5', 'CODE6'],
            };
            mockSetup2FA.mockResolvedValue(setupData);

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(mockSetup2FA).toHaveBeenCalled();
            });
        });
    });

    // ==================== 2FA Setup Flow ====================

    describe('2FA Setup Flow', () => {
        const setupData = {
            qr_code: 'data:image/png;base64,testqrcode',
            provisioning_uri: 'otpauth://totp/Ablage:test@test.com?secret=TESTSECRET123&issuer=Ablage',
            backup_codes: ['ABC123', 'DEF456', 'GHI789', 'JKL012', 'MNO345', 'PQR678'],
        };

        beforeEach(() => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: false,
                available: true,
                backup_codes_remaining: 0,
            });
            mockSetup2FA.mockResolvedValue(setupData);
        });

        it('zeigt QR-Code nach Setup-Start', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByAltText('2FA QR Code')).toBeInTheDocument();
            });
        });

        it('zeigt Backup-Codes nach Setup-Start', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByText('ABC123')).toBeInTheDocument();
                expect(screen.getByText('DEF456')).toBeInTheDocument();
            });
        });

        it('kann Backup-Codes kopieren', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /kopieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /kopieren/i }));
            });

            expect(mockWriteText).toHaveBeenCalledWith(
                setupData.backup_codes.join('\n')
            );
        });

        it('zeigt Bestätigungscode-Eingabe', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByPlaceholderText('000000')).toBeInTheDocument();
                expect(screen.getByRole('button', { name: /bestätigen/i })).toBeInTheDocument();
            });
        });

        it('verifiziert Code erfolgreich', async () => {
            mockVerify2FASetup.mockResolvedValue({ success: true });
            mockGet2FAStatus
                .mockResolvedValueOnce({ enabled: false, available: true, backup_codes_remaining: 0 })
                .mockResolvedValueOnce({ enabled: true, available: true, backup_codes_remaining: 6 });

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByPlaceholderText('000000')).toBeInTheDocument();
            });

            const input = screen.getByPlaceholderText('000000');
            await act(async () => {
                fireEvent.change(input, { target: { value: '123456' } });
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /bestätigen/i }));
            });

            await waitFor(() => {
                expect(mockVerify2FASetup).toHaveBeenCalledWith('123456');
            });
        });

        it('kann Setup abbrechen', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /abbrechen/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /abbrechen/i }));
            });

            await waitFor(() => {
                expect(screen.getByText('2FA ist deaktiviert')).toBeInTheDocument();
            });
        });
    });

    // ==================== 2FA Enabled State ====================

    describe('2FA aktiviert', () => {
        beforeEach(() => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: true,
                available: true,
                backup_codes_remaining: 5,
                setup_at: '2024-01-15T10:00:00Z',
            });
        });

        it('zeigt "2FA ist aktiviert" Status', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByText('2FA ist aktiviert')).toBeInTheDocument();
            });
        });

        it('zeigt Backup-Codes Anzahl', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByText('5 Backup-Codes verfügbar')).toBeInTheDocument();
            });
        });

        it('zeigt Deaktivieren-Button', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /2fa deaktivieren/i })).toBeInTheDocument();
            });
        });

        it('zeigt Warnung bei wenigen Backup-Codes', async () => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: true,
                available: true,
                backup_codes_remaining: 2,
                setup_at: '2024-01-15T10:00:00Z',
            });

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByText(/Sie haben nur noch 2 Backup-Codes/i)).toBeInTheDocument();
            });
        });
    });

    // ==================== Disable 2FA ====================

    describe('2FA deaktivieren', () => {
        beforeEach(() => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: true,
                available: true,
                backup_codes_remaining: 5,
                setup_at: '2024-01-15T10:00:00Z',
            });
        });

        it('öffnet Deaktivieren-Dialog', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /2fa deaktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /2fa deaktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByText('2FA wirklich deaktivieren?')).toBeInTheDocument();
            });
        });

        it('deaktiviert 2FA erfolgreich', async () => {
            mockDisable2FA.mockResolvedValue({ success: true });
            mockGet2FAStatus
                .mockResolvedValueOnce({ enabled: true, available: true, backup_codes_remaining: 5 })
                .mockResolvedValueOnce({ enabled: false, available: true, backup_codes_remaining: 0 });

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /2fa deaktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /2fa deaktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByPlaceholderText('Code eingeben')).toBeInTheDocument();
            });

            const input = screen.getByPlaceholderText('Code eingeben');
            await act(async () => {
                fireEvent.change(input, { target: { value: '123456' } });
            });

            // Find and click the confirm deactivate button in the dialog
            const deactivateButtons = screen.getAllByRole('button', { name: /deaktivieren/i });
            const confirmButton = deactivateButtons.find(btn =>
                btn.closest('[role="alertdialog"]')
            );

            if (confirmButton) {
                await act(async () => {
                    fireEvent.click(confirmButton);
                });
            }

            await waitFor(() => {
                expect(mockDisable2FA).toHaveBeenCalledWith('123456');
            });
        });
    });

    // ==================== Regenerate Backup Codes ====================

    describe('Backup-Codes regenerieren', () => {
        beforeEach(() => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: true,
                available: true,
                backup_codes_remaining: 2,
                setup_at: '2024-01-15T10:00:00Z',
            });
        });

        it('öffnet Regenerieren-Dialog', async () => {
            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /neu generieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /neu generieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByText('Backup-Codes neu generieren?')).toBeInTheDocument();
            });
        });

        it('generiert neue Backup-Codes erfolgreich', async () => {
            const newCodes = ['NEW001', 'NEW002', 'NEW003', 'NEW004', 'NEW005', 'NEW006'];
            mockRegenerateBackupCodes.mockResolvedValue(newCodes);

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /neu generieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /neu generieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByText('Backup-Codes neu generieren?')).toBeInTheDocument();
            });

            // Find input in the dialog
            const inputs = screen.getAllByPlaceholderText('000000');
            const dialogInput = inputs.find(input =>
                input.closest('[role="alertdialog"]')
            );

            if (dialogInput) {
                await act(async () => {
                    fireEvent.change(dialogInput, { target: { value: '123456' } });
                });
            }

            // Find and click the generate button
            const generateButton = screen.getByRole('button', { name: /generieren$/i });
            await act(async () => {
                fireEvent.click(generateButton);
            });

            await waitFor(() => {
                expect(mockRegenerateBackupCodes).toHaveBeenCalledWith('123456');
            });
        });

        it('zeigt neue Backup-Codes nach Regeneration', async () => {
            const newCodes = ['NEW001', 'NEW002', 'NEW003', 'NEW004', 'NEW005', 'NEW006'];
            mockRegenerateBackupCodes.mockResolvedValue(newCodes);

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /neu generieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /neu generieren/i }));
            });

            await waitFor(() => {
                const inputs = screen.getAllByPlaceholderText('000000');
                const dialogInput = inputs.find(input =>
                    input.closest('[role="alertdialog"]')
                );
                if (dialogInput) {
                    fireEvent.change(dialogInput, { target: { value: '123456' } });
                }
            });

            const generateButton = screen.getByRole('button', { name: /generieren$/i });
            await act(async () => {
                fireEvent.click(generateButton);
            });

            await waitFor(() => {
                expect(screen.getByText('Neue Backup-Codes!')).toBeInTheDocument();
            });
        });
    });

    // ==================== Error Handling ====================

    describe('Fehlerbehandlung', () => {
        it('zeigt Toast bei Status-Ladefehler', async () => {
            mockGet2FAStatus.mockRejectedValue(new Error('Network error'));

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(mockToast).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: 'Fehler',
                        variant: 'destructive',
                    })
                );
            });
        });

        it('zeigt Toast bei Setup-Fehler', async () => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: false,
                available: true,
                backup_codes_remaining: 0,
            });
            mockSetup2FA.mockRejectedValue(new Error('Setup failed'));

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(mockToast).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: 'Fehler',
                        description: '2FA-Setup konnte nicht gestartet werden.',
                        variant: 'destructive',
                    })
                );
            });
        });

        it('zeigt Toast bei Verifikations-Fehler', async () => {
            const setupData = {
                qr_code: 'data:image/png;base64,test',
                provisioning_uri: 'otpauth://totp/Test?secret=TEST&issuer=Test',
                backup_codes: ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'],
            };
            mockGet2FAStatus.mockResolvedValue({
                enabled: false,
                available: true,
                backup_codes_remaining: 0,
            });
            mockSetup2FA.mockResolvedValue(setupData);
            mockVerify2FASetup.mockRejectedValue(new Error('Invalid code'));

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /aktivieren/i })).toBeInTheDocument();
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /aktivieren/i }));
            });

            await waitFor(() => {
                expect(screen.getByPlaceholderText('000000')).toBeInTheDocument();
            });

            const input = screen.getByPlaceholderText('000000');
            await act(async () => {
                fireEvent.change(input, { target: { value: '123456' } });
            });

            await act(async () => {
                fireEvent.click(screen.getByRole('button', { name: /bestätigen/i }));
            });

            await waitFor(() => {
                expect(mockToast).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: 'Fehler',
                        description: 'Ungültiger Code. Bitte versuchen Sie es erneut.',
                        variant: 'destructive',
                    })
                );
            });
        });
    });

    // ==================== 2FA Not Available ====================

    describe('2FA nicht verfügbar', () => {
        it('zeigt Warnung wenn 2FA nicht verfügbar', async () => {
            mockGet2FAStatus.mockResolvedValue({
                enabled: false,
                available: false,
                backup_codes_remaining: 0,
            });

            render(<SecuritySettingsTab />);

            await waitFor(() => {
                expect(screen.getByText(/2FA ist auf diesem Server nicht verfügbar/i)).toBeInTheDocument();
            });
        });
    });
});
