import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BulkActionsBar } from '../components/BulkActionsBar';

// Mock the banking queries hooks
vi.mock('../hooks/use-banking-queries', () => ({
    useBulkEscalateDunnings: () => ({
        mutateAsync: vi.fn().mockResolvedValue({}),
        isPending: false,
    }),
    useBulkSendReminders: () => ({
        mutateAsync: vi.fn().mockResolvedValue({ total: 2, sent: 2, failed: 0, errors: [] }),
        isPending: false,
    }),
    useSetMahnstopp: () => ({
        mutateAsync: vi.fn().mockResolvedValue({}),
        isPending: false,
    }),
    useLiftMahnstopp: () => ({
        mutateAsync: vi.fn().mockResolvedValue({}),
        isPending: false,
    }),
}));

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

describe('BulkActionsBar', () => {
    const defaultProps = {
        selectedIds: ['dunning-1', 'dunning-2'],
        onClearSelection: vi.fn(),
        onActionComplete: vi.fn(),
    };

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('rendert nicht wenn keine IDs ausgewählt sind', () => {
        const { container } = render(
            <BulkActionsBar {...defaultProps} selectedIds={[]} />,
            { wrapper: createWrapper() }
        );

        expect(container.firstChild).toBeNull();
    });

    it('zeigt Anzahl ausgewählter Vorgänge', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        expect(screen.getByText('2 ausgewählt')).toBeInTheDocument();
    });

    it('zeigt Mahnung senden Button', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        expect(screen.getByRole('button', { name: /Mahnung senden/i })).toBeInTheDocument();
    });

    it('zeigt Eskalieren Button', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        expect(screen.getByRole('button', { name: /Eskalieren/i })).toBeInTheDocument();
    });

    it('zeigt Mahnstopp Button', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        expect(screen.getByRole('button', { name: /Mahnstopp/i })).toBeInTheDocument();
    });

    it('zeigt Auswahl aufheben Button', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        expect(screen.getByRole('button', { name: /Auswahl aufheben/i })).toBeInTheDocument();
    });

    it('ruft onClearSelection auf beim Klick auf Auswahl aufheben', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        fireEvent.click(screen.getByRole('button', { name: /Auswahl aufheben/i }));

        expect(defaultProps.onClearSelection).toHaveBeenCalled();
    });

    it('öffnet Eskalations-Bestätigungsdialog', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        fireEvent.click(screen.getByRole('button', { name: /Eskalieren/i }));

        expect(screen.getByText('Mahnvorgänge eskalieren?')).toBeInTheDocument();
    });

    it('öffnet Mahnstopp-Dialog', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        fireEvent.click(screen.getByRole('button', { name: /Mahnstopp/i }));

        expect(screen.getByText('Mahnstopp setzen')).toBeInTheDocument();
    });

    it('validiert Mahnstopp-Grund als Pflichtfeld', async () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        // Open dialog
        fireEvent.click(screen.getByRole('button', { name: /Mahnstopp/i }));

        // Try to submit without reason
        const submitButton = screen.getByRole('button', { name: /Mahnstopp setzen/i });
        expect(submitButton).toBeDisabled();
    });

    it('zeigt korrekten Text in Eskalations-Dialog', () => {
        render(<BulkActionsBar {...defaultProps} />, { wrapper: createWrapper() });

        fireEvent.click(screen.getByRole('button', { name: /Eskalieren/i }));

        expect(screen.getByText(/2 Mahnvorgänge auf die nächste Mahnstufe/i)).toBeInTheDocument();
    });

    it('verwendet korrekten Plural für einzelnen Vorgang', () => {
        render(
            <BulkActionsBar {...defaultProps} selectedIds={['dunning-1']} />,
            { wrapper: createWrapper() }
        );

        expect(screen.getByText('1 ausgewählt')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: /Eskalieren/i }));

        // Should use singular form
        expect(screen.getByText(/1 Mahnvorgang auf die nächste/i)).toBeInTheDocument();
    });
});
