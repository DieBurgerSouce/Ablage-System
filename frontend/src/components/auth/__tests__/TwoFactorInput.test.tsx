import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TwoFactorInput } from '../TwoFactorInput';

describe('TwoFactorInput', () => {
    const defaultProps = {
        onSubmit: vi.fn(),
        onCancel: vi.fn(),
        isLoading: false,
        error: null,
    };

    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Rendering', () => {
        it('rendert die 2FA-Code Eingabe standardmäßig', () => {
            render(<TwoFactorInput {...defaultProps} />);

            expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('000000')).toBeInTheDocument();
        });

        it('rendert den Bestätigen-Button', () => {
            render(<TwoFactorInput {...defaultProps} />);

            expect(screen.getByRole('button', { name: 'Bestätigen' })).toBeInTheDocument();
        });

        it('rendert den Abbrechen-Button', () => {
            render(<TwoFactorInput {...defaultProps} />);

            expect(screen.getByRole('button', { name: 'Abbrechen' })).toBeInTheDocument();
        });

        it('rendert den Backup-Code-Umschalter', () => {
            render(<TwoFactorInput {...defaultProps} />);

            expect(screen.getByRole('button', { name: 'Backup-Code verwenden' })).toBeInTheDocument();
        });
    });

    describe('TOTP Code Eingabe', () => {
        it('akzeptiert nur Ziffern für TOTP-Codes', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, 'abc123def456');

            expect(input).toHaveValue('123456');
        });

        it('begrenzt TOTP-Codes auf 6 Ziffern', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, '12345678');

            expect(input).toHaveValue('123456');
        });

        it('ruft onSubmit automatisch auf wenn 6 Ziffern eingegeben werden', async () => {
            const onSubmit = vi.fn();
            render(<TwoFactorInput {...defaultProps} onSubmit={onSubmit} />);

            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, '123456');

            await waitFor(() => {
                expect(onSubmit).toHaveBeenCalledWith('123456');
            });
        });

        it('deaktiviert den Submit-Button bei weniger als 6 Ziffern', () => {
            render(<TwoFactorInput {...defaultProps} />);

            const submitButton = screen.getByRole('button', { name: 'Bestätigen' });
            expect(submitButton).toBeDisabled();
        });

        it('aktiviert den Submit-Button bei 6 Ziffern', async () => {
            const onSubmit = vi.fn(); // Prevent auto-submit side effects
            render(<TwoFactorInput {...defaultProps} onSubmit={onSubmit} />);

            const input = screen.getByPlaceholderText('000000');
            fireEvent.change(input, { target: { value: '123456' } });

            const submitButton = screen.getByRole('button', { name: 'Bestätigen' });
            // Button should be enabled (auto-submit may have already triggered)
            await waitFor(() => {
                expect(submitButton).not.toBeDisabled();
            });
        });
    });

    describe('Backup-Code Modus', () => {
        it('wechselt zum Backup-Code Modus', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            const toggleButton = screen.getByRole('button', { name: 'Backup-Code verwenden' });
            await userEvent.click(toggleButton);

            expect(screen.getByText('Backup-Code eingeben')).toBeInTheDocument();
            expect(screen.getByPlaceholderText('XXXX-XXXX')).toBeInTheDocument();
        });

        it('akzeptiert alphanumerische Zeichen und Bindestriche für Backup-Codes', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            // Switch to backup code mode
            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const input = screen.getByPlaceholderText('XXXX-XXXX');
            await userEvent.type(input, 'ABCD-1234');

            expect(input).toHaveValue('ABCD-1234');
        });

        it('begrenzt Backup-Codes auf 9 Zeichen', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const input = screen.getByPlaceholderText('XXXX-XXXX');
            await userEvent.type(input, 'ABCDEFGHIJKL');

            expect(input).toHaveValue('ABCDEFGHI');
        });

        it('führt keinen Auto-Submit im Backup-Code Modus durch', async () => {
            const onSubmit = vi.fn();
            render(<TwoFactorInput {...defaultProps} onSubmit={onSubmit} />);

            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const input = screen.getByPlaceholderText('XXXX-XXXX');
            await userEvent.type(input, 'ABCD1234');

            // Wait a bit to ensure no auto-submit
            await new Promise(resolve => setTimeout(resolve, 100));
            expect(onSubmit).not.toHaveBeenCalled();
        });

        it('deaktiviert Submit bei weniger als 8 Zeichen im Backup-Modus', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const input = screen.getByPlaceholderText('XXXX-XXXX');
            await userEvent.type(input, 'ABC');

            const submitButton = screen.getByRole('button', { name: 'Bestätigen' });
            expect(submitButton).toBeDisabled();
        });

        it('wechselt zurück zum TOTP-Modus', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            // Switch to backup
            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));
            expect(screen.getByText('Backup-Code eingeben')).toBeInTheDocument();

            // Switch back to TOTP
            await userEvent.click(screen.getByRole('button', { name: 'Authenticator-App verwenden' }));
            expect(screen.getByText('2FA-Code eingeben')).toBeInTheDocument();
        });

        it('leert das Eingabefeld beim Moduswechsel', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            const input = screen.getByPlaceholderText('000000');
            await userEvent.type(input, '12345');

            // Switch mode
            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const backupInput = screen.getByPlaceholderText('XXXX-XXXX');
            expect(backupInput).toHaveValue('');
        });
    });

    describe('Loading State', () => {
        it('zeigt Lade-Indikator wenn isLoading=true', () => {
            render(<TwoFactorInput {...defaultProps} isLoading={true} />);

            expect(screen.getByText('Wird überprüft...')).toBeInTheDocument();
        });

        it('deaktiviert das Eingabefeld während des Ladens', () => {
            render(<TwoFactorInput {...defaultProps} isLoading={true} />);

            const input = screen.getByRole('textbox');
            expect(input).toBeDisabled();
        });

        it('deaktiviert alle Buttons während des Ladens', () => {
            render(<TwoFactorInput {...defaultProps} isLoading={true} />);

            const buttons = screen.getAllByRole('button');
            buttons.forEach(button => {
                expect(button).toBeDisabled();
            });
        });

        it('führt keinen Auto-Submit während des Ladens durch', async () => {
            const onSubmit = vi.fn();
            const { rerender } = render(
                <TwoFactorInput {...defaultProps} onSubmit={onSubmit} isLoading={true} />
            );

            const input = screen.getByRole('textbox');
            fireEvent.change(input, { target: { value: '123456' } });

            await new Promise(resolve => setTimeout(resolve, 100));
            expect(onSubmit).not.toHaveBeenCalled();
        });
    });

    describe('Error State', () => {
        it('zeigt Fehlermeldung an', () => {
            render(<TwoFactorInput {...defaultProps} error="Ungültiger Code" />);

            expect(screen.getByText('Ungültiger Code')).toBeInTheDocument();
        });

        it('zeigt keinen Fehler wenn error=null', () => {
            render(<TwoFactorInput {...defaultProps} error={null} />);

            expect(screen.queryByText('Ungültiger Code')).not.toBeInTheDocument();
        });
    });

    describe('User Interactions', () => {
        it('ruft onCancel auf beim Klick auf Abbrechen', async () => {
            const onCancel = vi.fn();
            render(<TwoFactorInput {...defaultProps} onCancel={onCancel} />);

            await userEvent.click(screen.getByRole('button', { name: 'Abbrechen' }));

            expect(onCancel).toHaveBeenCalled();
        });

        it('ruft onSubmit mit dem Code auf beim Form-Submit', async () => {
            const onSubmit = vi.fn();
            render(<TwoFactorInput {...defaultProps} onSubmit={onSubmit} />);

            const input = screen.getByPlaceholderText('000000');
            fireEvent.change(input, { target: { value: '123456' } });

            const form = input.closest('form');
            fireEvent.submit(form!);

            await waitFor(() => {
                expect(onSubmit).toHaveBeenCalledWith('123456');
            });
        });
    });

    describe('Accessibility', () => {
        it('hat ein verstecktes Label für das Eingabefeld', () => {
            render(<TwoFactorInput {...defaultProps} />);

            const label = screen.getByText('2FA-Code', { selector: '.sr-only' });
            expect(label).toBeInTheDocument();
        });

        it('hat autocomplete="one-time-code" für Browser-Autofill', () => {
            render(<TwoFactorInput {...defaultProps} />);

            const input = screen.getByRole('textbox');
            expect(input).toHaveAttribute('autocomplete', 'one-time-code');
        });

        it('verwendet inputMode="numeric" für TOTP', () => {
            render(<TwoFactorInput {...defaultProps} />);

            const input = screen.getByRole('textbox');
            expect(input).toHaveAttribute('inputMode', 'numeric');
        });

        it('verwendet inputMode="text" für Backup-Codes', async () => {
            render(<TwoFactorInput {...defaultProps} />);

            await userEvent.click(screen.getByRole('button', { name: 'Backup-Code verwenden' }));

            const input = screen.getByRole('textbox');
            expect(input).toHaveAttribute('inputMode', 'text');
        });
    });
});
