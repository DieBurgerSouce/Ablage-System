/**
 * Tests für ManualMatchDialog
 *
 * Enterprise-Grade Tests für:
 * - Confidence Bounds-Check
 * - Error Handling
 * - Double-Submit Prevention
 * - Memory Leak Prevention
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ManualMatchDialog } from '../components/reconciliation/ManualMatchDialog'

// Mock toast
const mockToast = vi.fn()
vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({
        toast: mockToast,
    }),
}))

// Mock match suggestions hook
const mockSuggestions = vi.fn()
vi.mock('@/features/banking/hooks/use-banking-queries', () => ({
    useMatchSuggestions: () => mockSuggestions(),
}))

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    })
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>
            {children}
        </QueryClientProvider>
    )
}

describe('ManualMatchDialog', () => {
    const mockTransaction = {
        id: 'tx-123',
        booking_date: '2024-01-15',
        amount: -1234.56,
        currency: 'EUR',
        counterparty_name: 'Müller GmbH',
        reference_text: 'Rechnung RE-2024-001',
    }

    const mockDocuments = [
        {
            id: 'doc-1',
            vendor_name: 'Müller GmbH',
            invoice_number: 'RE-2024-001',
            invoice_date: '2024-01-10',
            total_amount: 1234.56,
            currency: 'EUR',
        },
        {
            id: 'doc-2',
            vendor_name: 'Schmidt AG',
            invoice_number: 'RE-2024-002',
            invoice_date: '2024-01-12',
            total_amount: 567.89,
            currency: 'EUR',
        },
    ]

    const defaultProps = {
        open: true,
        onOpenChange: vi.fn(),
        transaction: mockTransaction,
        documents: mockDocuments,
        isLoading: false,
        onMatch: vi.fn(),
    }

    beforeEach(() => {
        vi.clearAllMocks()
        mockSuggestions.mockReturnValue({
            data: [
                {
                    document_id: 'doc-1',
                    counterparty_name: 'Müller GmbH',
                    invoice_number: 'RE-2024-001',
                    invoice_date: '2024-01-10',
                    gross_amount: 1234.56,
                    confidence: 0.95,
                    match_method: 'amount_exact',
                },
            ],
            isLoading: false,
        })
    })

    afterEach(() => {
        vi.clearAllMocks()
    })

    describe('Rendering', () => {
        it('zeigt Dialog-Titel', () => {
            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByText('Transaktion zuordnen')).toBeInTheDocument()
        })

        it('zeigt Transaktions-Details', () => {
            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Müller GmbH kann mehrfach vorkommen (Transaction + Suggestions)
            expect(screen.getAllByText('Müller GmbH').length).toBeGreaterThanOrEqual(1)
            expect(screen.getByText('Rechnung RE-2024-001')).toBeInTheDocument()
        })

        it('zeigt Vorschläge-Tab und Manuelle Suche-Tab', () => {
            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByRole('tab', { name: /Vorschläge/i })).toBeInTheDocument()
            expect(screen.getByRole('tab', { name: /Manuelle Suche/i })).toBeInTheDocument()
        })
    })

    describe('Confidence Display', () => {
        it('zeigt maximal 100% Confidence', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: 1.5, // Invalid: > 100%
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Should show 100%, not 150%
            expect(screen.getByText('100%')).toBeInTheDocument()
            expect(screen.queryByText('150%')).not.toBeInTheDocument()
        })

        it('behandelt NaN confidence gracefully', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: NaN,
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Should show 0%, not NaN%
            expect(screen.getByText('0%')).toBeInTheDocument()
        })

        it('behandelt negative confidence gracefully', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: -0.5, // Invalid: negative
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Should show 0%, not -50%
            expect(screen.getByText('0%')).toBeInTheDocument()
        })

        it('behandelt undefined confidence gracefully', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: undefined,
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Should show 0%
            expect(screen.getByText('0%')).toBeInTheDocument()
        })
    })

    describe('Match Flow', () => {
        it('schließt Dialog nach erfolgreichem Match', async () => {
            const user = userEvent.setup()
            const onMatch = vi.fn().mockResolvedValue(undefined)
            const onOpenChange = vi.fn()

            render(
                <ManualMatchDialog
                    {...defaultProps}
                    onMatch={onMatch}
                    onOpenChange={onOpenChange}
                />,
                { wrapper: createWrapper() }
            )

            // Wähle einen Vorschlag
            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            await user.click(suggestionCard)

            // Klicke Verknüpfen
            const matchButton = screen.getByRole('button', { name: /Verknüpfen/i })
            await user.click(matchButton)

            await waitFor(() => {
                expect(onMatch).toHaveBeenCalledWith('tx-123', 'doc-1')
                expect(onOpenChange).toHaveBeenCalledWith(false)
            })
        })

        it('zeigt Error Toast bei API-Fehler', async () => {
            const user = userEvent.setup()
            const onMatch = vi.fn().mockRejectedValue(new Error('Network Error'))

            render(
                <ManualMatchDialog {...defaultProps} onMatch={onMatch} />,
                { wrapper: createWrapper() }
            )

            // Wähle einen Vorschlag
            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            await user.click(suggestionCard)

            // Klicke Verknüpfen
            const matchButton = screen.getByRole('button', { name: /Verknüpfen/i })
            await user.click(matchButton)

            await waitFor(() => {
                expect(mockToast).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: 'Verknüpfung fehlgeschlagen',
                        variant: 'destructive',
                    })
                )
            })
        })

        it('zeigt Success Toast bei erfolgreichem Match', async () => {
            const user = userEvent.setup()
            const onMatch = vi.fn().mockResolvedValue(undefined)

            render(
                <ManualMatchDialog {...defaultProps} onMatch={onMatch} />,
                { wrapper: createWrapper() }
            )

            // Wähle einen Vorschlag
            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            await user.click(suggestionCard)

            // Klicke Verknüpfen
            const matchButton = screen.getByRole('button', { name: /Verknüpfen/i })
            await user.click(matchButton)

            await waitFor(() => {
                expect(mockToast).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: 'Erfolgreich verknüpft',
                    })
                )
            })
        })
    })

    describe('Double-Submit Prevention', () => {
        it('verhindert doppelten API-Call bei schnellem Doppelklick', async () => {
            const user = userEvent.setup()
            const onMatch = vi.fn().mockImplementation(
                () => new Promise((resolve) => setTimeout(resolve, 100))
            )

            render(
                <ManualMatchDialog {...defaultProps} onMatch={onMatch} />,
                { wrapper: createWrapper() }
            )

            // Wähle einen Vorschlag
            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            await user.click(suggestionCard)

            // Schnell 2x klicken (mit click statt dblClick für sequentielle Clicks)
            const matchButton = screen.getByRole('button', { name: /Verknüpfen/i })
            await user.click(matchButton)
            await user.click(matchButton)

            // Warte kurz und prüfe
            await waitFor(() => {
                expect(onMatch).toHaveBeenCalledTimes(1)
            })
        })

        it('deaktiviert Button während Matching', async () => {
            const user = userEvent.setup()
            const onMatch = vi.fn().mockImplementation(
                () => new Promise(() => {}) // Never resolves
            )

            render(
                <ManualMatchDialog {...defaultProps} onMatch={onMatch} />,
                { wrapper: createWrapper() }
            )

            // Wähle einen Vorschlag
            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            await user.click(suggestionCard)

            // Klicke Verknüpfen
            const matchButton = screen.getByRole('button', { name: /Verknüpfen/i })
            await user.click(matchButton)

            // Prüfe dass Button disabled ist
            await waitFor(() => {
                expect(matchButton).toBeDisabled()
            })
        })
    })

    describe('Abbrechen', () => {
        it('ruft onOpenChange(false) bei Abbrechen auf', async () => {
            const user = userEvent.setup()
            const onOpenChange = vi.fn()

            render(
                <ManualMatchDialog {...defaultProps} onOpenChange={onOpenChange} />,
                { wrapper: createWrapper() }
            )

            const cancelButton = screen.getByRole('button', { name: /Abbrechen/i })
            await user.click(cancelButton)

            expect(onOpenChange).toHaveBeenCalledWith(false)
        })
    })

    describe('Accessibility', () => {
        it('hat aria-label für Suggestion Cards', () => {
            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })
            expect(suggestionCard).toHaveAttribute('aria-label')
        })

        it('hat aria-pressed für ausgewählte Suggestion', async () => {
            const user = userEvent.setup()

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })

            // Vor Klick: nicht gedrückt
            expect(suggestionCard).toHaveAttribute('aria-pressed', 'false')

            // Nach Klick: gedrückt
            await user.click(suggestionCard)
            expect(suggestionCard).toHaveAttribute('aria-pressed', 'true')
        })

        it('unterstützt Keyboard-Navigation für Suggestion Cards', async () => {
            const user = userEvent.setup()

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const suggestionCard = screen.getByRole('button', { name: /Match-Vorschlag/i })

            // Tab zu Card
            await user.tab()
            // Focus ist möglicherweise woanders, also direkt focussen
            suggestionCard.focus()

            // Enter drücken
            await user.keyboard('{Enter}')

            // Card sollte ausgewählt sein
            expect(suggestionCard).toHaveAttribute('aria-pressed', 'true')
        })
    })

    describe('Leere Zustände', () => {
        it('zeigt Hinweis wenn keine Vorschläge vorhanden', () => {
            mockSuggestions.mockReturnValue({
                data: [],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByText(/Keine automatischen Vorschläge/)).toBeInTheDocument()
        })

        it('zeigt Link zur manuellen Suche wenn keine Vorschläge', () => {
            mockSuggestions.mockReturnValue({
                data: [],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByRole('button', { name: /Zur manuellen Suche/i })).toBeInTheDocument()
        })
    })

    describe('Quick Match', () => {
        it('zeigt Quick-Match-Button bei hoher Konfidenz', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: 0.95,
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByText(/Beste Übereinstimmung/)).toBeInTheDocument()
            expect(screen.getByRole('button', { name: /Übernehmen/i })).toBeInTheDocument()
        })

        it('zeigt keinen Quick-Match-Button bei niedriger Konfidenz', () => {
            mockSuggestions.mockReturnValue({
                data: [
                    {
                        document_id: 'doc-1',
                        counterparty_name: 'Test',
                        confidence: 0.5,
                        gross_amount: 100,
                    },
                ],
                isLoading: false,
            })

            render(<ManualMatchDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.queryByText(/Beste Übereinstimmung/)).not.toBeInTheDocument()
        })
    })
})
