import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SessionExpiredModal } from '../SessionExpiredModal';

// Mock TanStack Router
const mockNavigate = vi.fn();
vi.mock('@tanstack/react-router', () => ({
    useNavigate: () => mockNavigate,
}));

describe('SessionExpiredModal', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        // Clean up any event listeners
        vi.restoreAllMocks();
    });

    describe('Initial State', () => {
        it('rendert initial geschlossen', () => {
            render(<SessionExpiredModal />);

            expect(screen.queryByText('Sitzung abgelaufen')).not.toBeInTheDocument();
        });
    });

    describe('Event Handling', () => {
        it('öffnet sich beim session-expired Event', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByText('Sitzung abgelaufen')).toBeInTheDocument();
            });
        });

        it('zeigt die korrekte Beschreibung', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(
                    screen.getByText('Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.')
                ).toBeInTheDocument();
            });
        });

        it('zeigt den Erneut-anmelden-Button', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByRole('button', { name: 'Erneut anmelden' })).toBeInTheDocument();
            });
        });
    });

    describe('Navigation', () => {
        it('navigiert zu /login beim Klick auf Erneut anmelden', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByRole('button', { name: 'Erneut anmelden' })).toBeInTheDocument();
            });

            fireEvent.click(screen.getByRole('button', { name: 'Erneut anmelden' }));

            expect(mockNavigate).toHaveBeenCalledWith({ to: '/login' });
        });

        it('schließt das Modal nach Navigation', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByText('Sitzung abgelaufen')).toBeInTheDocument();
            });

            fireEvent.click(screen.getByRole('button', { name: 'Erneut anmelden' }));

            await waitFor(() => {
                expect(screen.queryByText('Sitzung abgelaufen')).not.toBeInTheDocument();
            });
        });
    });

    describe('Cleanup', () => {
        it('entfernt Event-Listener beim Unmount', () => {
            const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

            const { unmount } = render(<SessionExpiredModal />);
            unmount();

            expect(removeEventListenerSpy).toHaveBeenCalledWith(
                'session-expired',
                expect.any(Function)
            );
        });
    });

    describe('Multiple Events', () => {
        it('reagiert auf mehrere session-expired Events', async () => {
            render(<SessionExpiredModal />);

            // First event - open
            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByText('Sitzung abgelaufen')).toBeInTheDocument();
            });

            // Close via button
            fireEvent.click(screen.getByRole('button', { name: 'Erneut anmelden' }));

            await waitFor(() => {
                expect(screen.queryByText('Sitzung abgelaufen')).not.toBeInTheDocument();
            });

            // Second event - should open again
            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByText('Sitzung abgelaufen')).toBeInTheDocument();
            });
        });
    });

    describe('Accessibility', () => {
        it('hat eine Dialogrolle', async () => {
            render(<SessionExpiredModal />);

            act(() => {
                window.dispatchEvent(new CustomEvent('session-expired'));
            });

            await waitFor(() => {
                expect(screen.getByRole('dialog')).toBeInTheDocument();
            });
        });
    });
});
