import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EmptyState, EmptyStatePresets } from '../empty-state'
import { Search } from 'lucide-react'

describe('EmptyState Component', () => {
    describe('Basic Rendering', () => {
        it('renders title and description', () => {
            render(
                <EmptyState
                    title="Keine Dokumente"
                    description="Laden Sie Ihr erstes Dokument hoch."
                />
            )

            expect(screen.getByText('Keine Dokumente')).toBeInTheDocument()
            expect(screen.getByText('Laden Sie Ihr erstes Dokument hoch.')).toBeInTheDocument()
        })

        it('renders without description', () => {
            render(<EmptyState title="Keine Daten" />)

            expect(screen.getByText('Keine Daten')).toBeInTheDocument()
        })

        it('renders with custom icon', () => {
            render(
                <EmptyState
                    title="Suche"
                    icon={Search}
                />
            )

            expect(screen.getByText('Suche')).toBeInTheDocument()
        })
    })

    describe('Variants', () => {
        it('renders search variant', () => {
            render(
                <EmptyState
                    variant="search"
                    title="Keine Ergebnisse"
                />
            )

            expect(screen.getByText('Keine Ergebnisse')).toBeInTheDocument()
        })

        it('renders error variant', () => {
            render(
                <EmptyState
                    variant="error"
                    title="Fehler aufgetreten"
                />
            )

            expect(screen.getByText('Fehler aufgetreten')).toBeInTheDocument()
        })

        it('renders upload variant', () => {
            render(
                <EmptyState
                    variant="upload"
                    title="Bereit zum Upload"
                />
            )

            expect(screen.getByText('Bereit zum Upload')).toBeInTheDocument()
        })
    })

    describe('Sizes', () => {
        it('renders small size', () => {
            const { container } = render(
                <EmptyState title="Klein" size="sm" />
            )

            expect(container.firstChild).toHaveClass('p-6')
        })

        it('renders medium size (default)', () => {
            const { container } = render(
                <EmptyState title="Mittel" />
            )

            expect(container.firstChild).toHaveClass('p-8')
        })

        it('renders large size', () => {
            const { container } = render(
                <EmptyState title="Gross" size="lg" />
            )

            expect(container.firstChild).toHaveClass('p-12')
        })
    })

    describe('Actions', () => {
        it('renders action button and handles click', () => {
            const handleClick = vi.fn()
            render(
                <EmptyState
                    title="Test"
                    action={{
                        label: 'Aktion ausführen',
                        onClick: handleClick,
                    }}
                />
            )

            const button = screen.getByText('Aktion ausführen')
            expect(button).toBeInTheDocument()

            fireEvent.click(button)
            expect(handleClick).toHaveBeenCalledTimes(1)
        })

        it('renders secondary action', () => {
            const handlePrimary = vi.fn()
            const handleSecondary = vi.fn()
            render(
                <EmptyState
                    title="Test"
                    action={{
                        label: 'Primaer',
                        onClick: handlePrimary,
                    }}
                    secondaryAction={{
                        label: 'Sekundaer',
                        onClick: handleSecondary,
                    }}
                />
            )

            expect(screen.getByText('Primaer')).toBeInTheDocument()
            expect(screen.getByText('Sekundaer')).toBeInTheDocument()
        })
    })

    describe('Presets', () => {
        it('generates noDocuments preset', () => {
            const onUpload = vi.fn()
            const preset = EmptyStatePresets.noDocuments(onUpload)

            expect(preset.title).toBe('Noch keine Dokumente')
            expect(preset.variant).toBe('document')
            expect(preset.action?.label).toBe('Dokument hochladen')
        })

        it('generates noSearchResults preset', () => {
            const preset = EmptyStatePresets.noSearchResults('test')

            expect(preset.title).toBe('Keine Ergebnisse gefunden')
            expect(preset.description).toContain('test')
        })

        it('generates searchPrompt preset', () => {
            const preset = EmptyStatePresets.searchPrompt()

            expect(preset.title).toBe('Dokumente durchsuchen')
            expect(preset.variant).toBe('search')
        })

        it('generates loadError preset with retry action', () => {
            const onRetry = vi.fn()
            const preset = EmptyStatePresets.loadError(onRetry)

            expect(preset.title).toBe('Fehler beim Laden')
            expect(preset.variant).toBe('error')
            expect(preset.action?.label).toBe('Erneut versuchen')
        })
    })

    describe('Accessibility', () => {
        it('has proper heading structure', () => {
            render(
                <EmptyState
                    title="Test Titel"
                    description="Test Beschreibung"
                />
            )

            const heading = screen.getByRole('heading', { level: 3 })
            expect(heading).toHaveTextContent('Test Titel')
        })
    })
})
