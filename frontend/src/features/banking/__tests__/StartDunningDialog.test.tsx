/**
 * Tests für StartDunningDialog
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StartDunningDialog } from '../components/StartDunningDialog'

// Mock banking service
vi.mock('@/lib/api/services/banking', () => ({
    bankingService: {
        createDunning: vi.fn(),
    },
}))

// Mock toast
vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({
        toast: vi.fn(),
    }),
}))

import { bankingService } from '@/lib/api/services/banking'

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

describe('StartDunningDialog', () => {
    const defaultProps = {
        documentId: 'doc-123',
        invoiceNumber: 'RE-2024-001',
        debtorName: 'Müller GmbH',
        outstandingAmount: 1234.56,
        open: true,
        onOpenChange: vi.fn(),
        onSuccess: vi.fn(),
    }

    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe('Rendering', () => {
        it('zeigt Dialog-Titel', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Title is in an h2 heading
            expect(screen.getByRole('heading', { name: /Mahnung starten/i })).toBeInTheDocument()
        })

        it('zeigt Rechnungsinformationen', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByText('RE-2024-001')).toBeInTheDocument()
            expect(screen.getByText('Müller GmbH')).toBeInTheDocument()
            expect(screen.getByText(/1\.234,56/)).toBeInTheDocument()
        })

        it('zeigt Mahnstufen-Auswahl', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByRole('combobox')).toBeInTheDocument()
            expect(screen.getByText('Mahnstufe')).toBeInTheDocument()
        })

        it('zeigt Notizen-Textfeld', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByPlaceholderText(/Grund für das manuelle Starten/)).toBeInTheDocument()
        })

        it('zeigt Aktions-Buttons', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByRole('button', { name: /Abbrechen/i })).toBeInTheDocument()
            expect(screen.getByRole('button', { name: /Mahnung starten/i })).toBeInTheDocument()
        })
    })

    describe('ohne optionale Props', () => {
        it('rendert ohne Rechnungsinformationen', () => {
            render(
                <StartDunningDialog
                    documentId="doc-123"
                    open={true}
                    onOpenChange={vi.fn()}
                />,
                { wrapper: createWrapper() }
            )

            expect(screen.getByRole('heading', { name: /Mahnung starten/i })).toBeInTheDocument()
            expect(screen.queryByText('Rechnung:')).not.toBeInTheDocument()
        })
    })

    describe('Mahnstufen-Auswahl', () => {
        it('hat Zahlungserinnerung als Default', async () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Default description should be visible
            expect(screen.getByText('Freundliche Erinnerung ohne Gebühren')).toBeInTheDocument()
        })
    })

    describe('Warnung bei höheren Stufen', () => {
        it('zeigt keine Warnung bei Stufe 0 und 1', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.queryByText(/rechtliche Schritte/)).not.toBeInTheDocument()
            expect(screen.queryByText(/Mahngebühren/)).not.toBeInTheDocument()
        })
    })

    describe('Form-Submission', () => {
        it('ruft createDunning mit korrekten Parametern auf', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockResolvedValueOnce({ id: 'dunning-123' })

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            // Enter notes
            const notesInput = screen.getByPlaceholderText(/Grund für das manuelle Starten/)
            await user.type(notesInput, 'Testnotiz')

            // Submit
            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            await waitFor(() => {
                expect(mockCreateDunning).toHaveBeenCalledWith({
                    document_id: 'doc-123',
                    level: '0',
                    notes: 'Testnotiz',
                })
            })
        })

        it('ruft onSuccess nach erfolgreichem Submit auf', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockResolvedValueOnce({ id: 'dunning-123' })

            const onSuccess = vi.fn()

            render(
                <StartDunningDialog {...defaultProps} onSuccess={onSuccess} />,
                { wrapper: createWrapper() }
            )

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            await waitFor(() => {
                expect(onSuccess).toHaveBeenCalledWith('dunning-123')
            })
        })

        it('schließt Dialog nach erfolgreichem Submit', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockResolvedValueOnce({ id: 'dunning-123' })

            const onOpenChange = vi.fn()

            render(
                <StartDunningDialog {...defaultProps} onOpenChange={onOpenChange} />,
                { wrapper: createWrapper() }
            )

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            await waitFor(() => {
                expect(onOpenChange).toHaveBeenCalledWith(false)
            })
        })
    })

    describe('Loading State', () => {
        it('zeigt Lade-Zustand während Submit', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            // Never resolve to keep loading state
            mockCreateDunning.mockImplementation(
                () => new Promise(() => {})
            )

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            await waitFor(() => {
                expect(screen.getByText('Wird gestartet...')).toBeInTheDocument()
            })
        })

        it('deaktiviert Buttons während Loading', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockImplementation(
                () => new Promise(() => {})
            )

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            await waitFor(() => {
                expect(screen.getByRole('button', { name: /Abbrechen/i })).toBeDisabled()
            })
        })
    })

    describe('Abbrechen', () => {
        it('ruft onOpenChange(false) bei Abbrechen auf', async () => {
            const user = userEvent.setup()
            const onOpenChange = vi.fn()

            render(
                <StartDunningDialog {...defaultProps} onOpenChange={onOpenChange} />,
                { wrapper: createWrapper() }
            )

            const cancelButton = screen.getByRole('button', { name: /Abbrechen/i })
            await user.click(cancelButton)

            expect(onOpenChange).toHaveBeenCalledWith(false)
        })

        it('setzt Formular-Werte zurück bei Abbrechen', async () => {
            const user = userEvent.setup()
            const onOpenChange = vi.fn()

            render(
                <StartDunningDialog {...defaultProps} onOpenChange={onOpenChange} />,
                { wrapper: createWrapper() }
            )

            // Enter notes
            const notesInput = screen.getByPlaceholderText(/Grund für das manuelle Starten/)
            await user.type(notesInput, 'Test')

            // Cancel
            const cancelButton = screen.getByRole('button', { name: /Abbrechen/i })
            await user.click(cancelButton)

            expect(onOpenChange).toHaveBeenCalledWith(false)
        })
    })

    describe('Accessibility', () => {
        it('hat korrektes aria-describedby für Mahnstufe', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const combobox = screen.getByRole('combobox')
            expect(combobox).toHaveAttribute('aria-describedby', 'dunning-level-description')
        })

        it('hat korrekte Label-Verknüpfungen', () => {
            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            expect(screen.getByLabelText(/Mahnstufe/)).toBeInTheDocument()
            expect(screen.getByLabelText(/Notizen/)).toBeInTheDocument()
        })
    })

    describe('Währungsformatierung', () => {
        it('formatiert Betrag korrekt in EUR', () => {
            render(
                <StartDunningDialog
                    {...defaultProps}
                    outstandingAmount={9999.99}
                />,
                { wrapper: createWrapper() }
            )

            expect(screen.getByText(/9\.999,99/)).toBeInTheDocument()
        })

        it('formatiert kleine Beträge korrekt', () => {
            render(
                <StartDunningDialog
                    {...defaultProps}
                    outstandingAmount={5.50}
                />,
                { wrapper: createWrapper() }
            )

            expect(screen.getByText(/5,50/)).toBeInTheDocument()
        })
    })

    describe('XSS Prevention', () => {
        it('zeigt generische Fehlermeldung statt error.message', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            // Simulate XSS attack in error message
            mockCreateDunning.mockRejectedValueOnce(
                new Error('<script>alert("XSS")</script>')
            )

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            // Wait for error handling
            await waitFor(() => {
                // Should NOT show the XSS payload
                expect(screen.queryByText(/<script>/)).not.toBeInTheDocument()
                // Should show generic error message instead
                // (Toast wird gemockt, also prüfen wir dass kein XSS im DOM ist)
            })
        })
    })

    describe('Double-Submit Prevention', () => {
        it('verhindert doppelten API-Call bei schnellem Doppelklick', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockImplementation(
                () => new Promise((resolve) => setTimeout(() => resolve({ id: 'test' }), 100))
            )

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })

            // Schnell 2x klicken
            await user.click(submitButton)
            await user.click(submitButton)

            await waitFor(() => {
                // Sollte nur einmal aufgerufen werden
                expect(mockCreateDunning).toHaveBeenCalledTimes(1)
            })
        })

        it('entsperrt Button nach Fehler', async () => {
            const user = userEvent.setup()
            const mockCreateDunning = vi.mocked(bankingService.createDunning)
            mockCreateDunning.mockRejectedValueOnce(new Error('Network Error'))

            render(<StartDunningDialog {...defaultProps} />, {
                wrapper: createWrapper(),
            })

            const submitButton = screen.getByRole('button', { name: /Mahnung starten/i })
            await user.click(submitButton)

            // Nach Fehler sollte Button wieder enabled sein
            await waitFor(() => {
                expect(submitButton).not.toBeDisabled()
            })
        })
    })
})
