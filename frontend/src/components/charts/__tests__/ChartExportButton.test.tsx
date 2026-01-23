/**
 * Chart Export Button Component Unit Tests
 *
 * Enterprise-Level Tests für die Chart-Export-Button-Komponente.
 * Testet UI-Rendering, Export-Funktionen und Benutzerinteraktionen.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChartExportButton, SimpleChartExportButton } from '../ChartExportButton'

// Mock chart-export utilities
vi.mock('@/lib/chart-export', () => ({
  exportElement: vi.fn(),
  copyChartToClipboard: vi.fn(),
}))

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import { exportElement, copyChartToClipboard } from '@/lib/chart-export'
import { toast } from 'sonner'

describe('ChartExportButton', () => {
  let mockRef: React.RefObject<HTMLElement>
  let mockElement: HTMLDivElement

  beforeEach(() => {
    vi.clearAllMocks()

    mockElement = document.createElement('div')
    mockRef = { current: mockElement }
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ==========================================================================
  // Rendering Tests
  // ==========================================================================

  describe('Rendering', () => {
    it('rendert Button mit Standard-Content', () => {
      render(<ChartExportButton elementRef={mockRef} />)

      expect(screen.getByRole('button')).toBeInTheDocument()
      expect(screen.getByText('Exportieren')).toBeInTheDocument()
    })

    it('rendert mit custom children', () => {
      render(
        <ChartExportButton elementRef={mockRef}>
          Custom Export
        </ChartExportButton>
      )

      expect(screen.getByText('Custom Export')).toBeInTheDocument()
    })

    it('rendert mit korrekter aria-label', () => {
      render(<ChartExportButton elementRef={mockRef} />)

      expect(screen.getByRole('button')).toHaveAttribute('aria-label', 'Chart exportieren')
    })

    it('respektiert disabled prop', () => {
      render(<ChartExportButton elementRef={mockRef} disabled />)

      expect(screen.getByRole('button')).toBeDisabled()
    })

    it('wendet custom className an', () => {
      render(<ChartExportButton elementRef={mockRef} className="custom-class" />)

      expect(screen.getByRole('button')).toHaveClass('custom-class')
    })
  })

  // ==========================================================================
  // Dropdown Menu Tests
  // ==========================================================================

  describe('Dropdown Menu', () => {
    it('öffnet Dropdown bei Klick', async () => {
      const user = userEvent.setup()
      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
        expect(screen.getByText('Als JPEG')).toBeInTheDocument()
        expect(screen.getByText('Als SVG')).toBeInTheDocument()
      })
    })

    it('zeigt Copy-Option standardmäßig', async () => {
      const user = userEvent.setup()
      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('In Zwischenablage kopieren')).toBeInTheDocument()
      })
    })

    it('versteckt Copy-Option wenn showCopyOption=false', async () => {
      const user = userEvent.setup()
      render(<ChartExportButton elementRef={mockRef} showCopyOption={false} />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.queryByText('In Zwischenablage kopieren')).not.toBeInTheDocument()
      })
    })

    it('zeigt nur spezifizierte Formate', async () => {
      const user = userEvent.setup()
      render(<ChartExportButton elementRef={mockRef} formats={['png']} />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
        expect(screen.queryByText('Als JPEG')).not.toBeInTheDocument()
        expect(screen.queryByText('Als SVG')).not.toBeInTheDocument()
      })
    })
  })

  // ==========================================================================
  // Export Tests
  // ==========================================================================

  describe('Export Funktionalität', () => {
    it('ruft exportElement bei Format-Auswahl auf', async () => {
      const user = userEvent.setup()
      vi.mocked(exportElement).mockResolvedValue({
        success: true,
        fileName: 'chart.png',
      })

      render(<ChartExportButton elementRef={mockRef} fileName="test-chart" />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(exportElement).toHaveBeenCalledWith(
          mockElement,
          expect.objectContaining({
            format: 'png',
            fileName: 'test-chart',
          })
        )
      })
    })

    it('zeigt Success-Toast bei erfolgreichem Export', async () => {
      const user = userEvent.setup()
      vi.mocked(exportElement).mockResolvedValue({
        success: true,
        fileName: 'chart.png',
      })

      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          'Chart als PNG exportiert',
          expect.objectContaining({
            description: 'chart.png',
          })
        )
      })
    })

    it('zeigt Error-Toast bei fehlgeschlagenem Export', async () => {
      const user = userEvent.setup()
      vi.mocked(exportElement).mockResolvedValue({
        success: false,
        error: 'Export fehlgeschlagen',
      })

      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith(
          'Export fehlgeschlagen',
          expect.objectContaining({
            description: 'Export fehlgeschlagen',
          })
        )
      })
    })

    it('zeigt Error wenn Ref null ist', async () => {
      const user = userEvent.setup()
      const nullRef = { current: null }

      render(<ChartExportButton elementRef={nullRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Chart nicht gefunden')
      })
    })

    it('ruft onExportStart Callback auf', async () => {
      const user = userEvent.setup()
      const onExportStart = vi.fn()
      vi.mocked(exportElement).mockResolvedValue({
        success: true,
        fileName: 'chart.png',
      })

      render(<ChartExportButton elementRef={mockRef} onExportStart={onExportStart} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(onExportStart).toHaveBeenCalled()
      })
    })

    it('ruft onExportComplete Callback auf', async () => {
      const user = userEvent.setup()
      const onExportComplete = vi.fn()
      vi.mocked(exportElement).mockResolvedValue({
        success: true,
        fileName: 'chart.png',
      })

      render(<ChartExportButton elementRef={mockRef} onExportComplete={onExportComplete} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('Als PNG')).toBeInTheDocument()
      })

      await user.click(screen.getByText('Als PNG'))

      await waitFor(() => {
        expect(onExportComplete).toHaveBeenCalledWith(
          expect.objectContaining({ success: true })
        )
      })
    })
  })

  // ==========================================================================
  // Clipboard Tests
  // ==========================================================================

  describe('Clipboard Funktionalität', () => {
    it('ruft copyChartToClipboard bei Klick auf', async () => {
      const user = userEvent.setup()
      vi.mocked(copyChartToClipboard).mockResolvedValue({ success: true })

      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('In Zwischenablage kopieren')).toBeInTheDocument()
      })

      await user.click(screen.getByText('In Zwischenablage kopieren'))

      await waitFor(() => {
        expect(copyChartToClipboard).toHaveBeenCalledWith(mockElement, {})
      })
    })

    it('zeigt Success-Toast bei erfolgreichem Kopieren', async () => {
      const user = userEvent.setup()
      vi.mocked(copyChartToClipboard).mockResolvedValue({ success: true })

      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('In Zwischenablage kopieren')).toBeInTheDocument()
      })

      await user.click(screen.getByText('In Zwischenablage kopieren'))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Chart in Zwischenablage kopiert')
      })
    })

    it('zeigt Error-Toast bei fehlgeschlagenem Kopieren', async () => {
      const user = userEvent.setup()
      vi.mocked(copyChartToClipboard).mockResolvedValue({
        success: false,
        error: 'Clipboard API nicht verfügbar'
      })

      render(<ChartExportButton elementRef={mockRef} />)

      await user.click(screen.getByRole('button'))
      await waitFor(() => {
        expect(screen.getByText('In Zwischenablage kopieren')).toBeInTheDocument()
      })

      await user.click(screen.getByText('In Zwischenablage kopieren'))

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('Kopieren fehlgeschlagen', {
          description: 'Clipboard API nicht verfügbar',
        })
      })
    })
  })
})

// ==========================================================================
// SimpleChartExportButton Tests
// ==========================================================================

describe('SimpleChartExportButton', () => {
  let mockRef: React.RefObject<HTMLElement>
  let mockElement: HTMLDivElement

  beforeEach(() => {
    vi.clearAllMocks()

    mockElement = document.createElement('div')
    mockRef = { current: mockElement }
  })

  describe('Rendering', () => {
    it('rendert Button mit Format-Label', () => {
      render(<SimpleChartExportButton elementRef={mockRef} format="png" />)

      expect(screen.getByRole('button')).toBeInTheDocument()
      expect(screen.getByText('PNG')).toBeInTheDocument()
    })

    it('rendert mit custom children', () => {
      render(
        <SimpleChartExportButton elementRef={mockRef}>
          Download PNG
        </SimpleChartExportButton>
      )

      expect(screen.getByText('Download PNG')).toBeInTheDocument()
    })

    it('hat korrekte aria-label', () => {
      render(<SimpleChartExportButton elementRef={mockRef} format="jpeg" />)

      expect(screen.getByRole('button')).toHaveAttribute(
        'aria-label',
        'Chart als JPEG exportieren'
      )
    })
  })

  describe('Export Funktionalität', () => {
    it('exportiert direkt bei Klick ohne Dropdown', async () => {
      const user = userEvent.setup()
      vi.mocked(exportElement).mockResolvedValue({
        success: true,
        fileName: 'chart.png',
      })

      render(<SimpleChartExportButton elementRef={mockRef} format="png" />)

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(exportElement).toHaveBeenCalledWith(
          mockElement,
          expect.objectContaining({
            format: 'png',
          })
        )
      })
    })

    it('zeigt Loader während Export', async () => {
      const user = userEvent.setup()
      let resolveExport: (value: { success: boolean; fileName?: string }) => void
      vi.mocked(exportElement).mockImplementation(
        () => new Promise((resolve) => {
          resolveExport = resolve
        })
      )

      render(<SimpleChartExportButton elementRef={mockRef} />)

      const button = screen.getByRole('button')
      await user.click(button)

      // Button should be disabled during export
      expect(button).toBeDisabled()

      // Resolve the export
      resolveExport!({ success: true, fileName: 'chart.png' })

      await waitFor(() => {
        expect(button).not.toBeDisabled()
      })
    })
  })
})
