/**
 * Responsive Table Component Unit Tests
 *
 * Enterprise-Level Tests für die mobile-responsive Tabellen-Komponente.
 * Testet Desktop-/Mobile-Rendering, Card-Layout und mobileLabel-Funktionalität.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  ResponsiveTable,
  ResponsiveTableHeader,
  ResponsiveTableBody,
  ResponsiveTableRow,
  ResponsiveTableHead,
  ResponsiveTableCell,
  ResponsiveTableCaption,
} from '../responsive-table'

describe('ResponsiveTable', () => {
  const originalInnerWidth = window.innerWidth

  beforeEach(() => {
    // Default to desktop width
    Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true, writable: true })
  })

  afterEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, configurable: true })
    vi.restoreAllMocks()
  })

  // ==========================================================================
  // Desktop Rendering Tests
  // ==========================================================================

  describe('Desktop Rendering', () => {
    it('rendert als HTML-Tabelle auf Desktop', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Name</ResponsiveTableHead>
              <ResponsiveTableHead>Email</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Max Mustermann</ResponsiveTableCell>
              <ResponsiveTableCell>max@example.de</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('table')).toBeInTheDocument()
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Email')).toBeInTheDocument()
      expect(screen.getByText('Max Mustermann')).toBeInTheDocument()
      expect(screen.getByText('max@example.de')).toBeInTheDocument()
    })

    it('rendert Header-Zeilen korrekt', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Header 1</ResponsiveTableHead>
              <ResponsiveTableHead>Header 2</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
        </ResponsiveTable>
      )

      const headerCells = screen.getAllByRole('columnheader')
      expect(headerCells).toHaveLength(2)
    })

    it('rendert Body-Zeilen korrekt', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell 1</ResponsiveTableCell>
              <ResponsiveTableCell>Cell 2</ResponsiveTableCell>
            </ResponsiveTableRow>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell 3</ResponsiveTableCell>
              <ResponsiveTableCell>Cell 4</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      const rows = screen.getAllByRole('row')
      expect(rows).toHaveLength(2)
    })

    it('rendert Caption korrekt', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableCaption>Tabellen-Beschreibung</ResponsiveTableCaption>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByText('Tabellen-Beschreibung')).toBeInTheDocument()
    })
  })

  // ==========================================================================
  // Mobile Rendering Tests
  // ==========================================================================

  describe('Mobile Rendering', () => {
    beforeEach(() => {
      Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
      window.dispatchEvent(new Event('resize'))
    })

    it('rendert als Card-Layout auf Mobile', async () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Name</ResponsiveTableHead>
              <ResponsiveTableHead>Email</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Max Mustermann</ResponsiveTableCell>
              <ResponsiveTableCell>max@example.de</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      // Wait for resize to take effect
      await waitFor(() => {
        // On mobile, table should not be rendered
        expect(screen.queryByRole('table')).not.toBeInTheDocument()
      })

      // Content should still be visible
      expect(screen.getByText('Max Mustermann')).toBeInTheDocument()
      expect(screen.getByText('max@example.de')).toBeInTheDocument()
    })

    it('zeigt Header-Labels in Card-Layout wenn headers prop gesetzt', async () => {
      render(
        <ResponsiveTable headers={['Name']}>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Name</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Max Mustermann</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await waitFor(() => {
        // Header label should be shown in card via headers prop
        expect(screen.getByText('Name')).toBeInTheDocument()
        expect(screen.getByText('Max Mustermann')).toBeInTheDocument()
      })
    })

    it('versteckt Table-Header auf Mobile', async () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Versteckter Header</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await waitFor(() => {
        // Header row should not be rendered as columnheader
        expect(screen.queryByRole('columnheader')).not.toBeInTheDocument()
      })
    })
  })

  // ==========================================================================
  // mobileLabel Tests
  // ==========================================================================

  describe('mobileLabel Prop', () => {
    beforeEach(() => {
      Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
      window.dispatchEvent(new Event('resize'))
    })

    it('verwendet mobileLabel statt Header wenn angegeben', async () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Long Header Name</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell mobileLabel="Kurz">
                Cell Content
              </ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await waitFor(() => {
        // mobileLabel should be used instead of header
        expect(screen.getByText('Kurz')).toBeInTheDocument()
        expect(screen.queryByText('Long Header Name')).not.toBeInTheDocument()
      })
    })

    it('fällt auf Header aus headers prop zurück wenn kein mobileLabel', async () => {
      render(
        <ResponsiveTable headers={['Fallback Header']}>
          <ResponsiveTableHeader>
            <ResponsiveTableRow>
              <ResponsiveTableHead>Fallback Header</ResponsiveTableHead>
            </ResponsiveTableRow>
          </ResponsiveTableHeader>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell Content</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await waitFor(() => {
        expect(screen.getByText('Fallback Header')).toBeInTheDocument()
      })
    })
  })

  // ==========================================================================
  // Interaction Tests
  // ==========================================================================

  describe('Row Click Handling', () => {
    it('ruft onRowClick bei Klick auf Zeile auf (Desktop)', async () => {
      const user = userEvent.setup()
      const handleRowClick = vi.fn()

      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow onRowClick={handleRowClick}>
              <ResponsiveTableCell>Clickable Row</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await user.click(screen.getByText('Clickable Row'))

      expect(handleRowClick).toHaveBeenCalled()
    })

    it('ruft onRowClick bei Klick auf Card auf (Mobile)', async () => {
      Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
      window.dispatchEvent(new Event('resize'))

      const user = userEvent.setup()
      const handleRowClick = vi.fn()

      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow onRowClick={handleRowClick}>
              <ResponsiveTableCell>Clickable Card</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      await waitFor(async () => {
        await user.click(screen.getByText('Clickable Card'))
        expect(handleRowClick).toHaveBeenCalled()
      })
    })
  })

  // ==========================================================================
  // CSS Class Tests
  // ==========================================================================

  describe('CSS Classes', () => {
    it('wendet custom className auf wrapper div an', () => {
      render(
        <ResponsiveTable className="custom-table-class">
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      // className is applied to the wrapper div, not the table element
      const wrapper = screen.getByRole('table').closest('.custom-table-class')
      expect(wrapper).toBeInTheDocument()
    })

    it('wendet custom className auf Cell an', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell className="custom-cell-class">
                Cell
              </ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('cell')).toHaveClass('custom-cell-class')
    })

    it('wendet cursor-pointer Klasse bei onRowClick an', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow onRowClick={() => {}}>
              <ResponsiveTableCell>Clickable</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('row')).toHaveClass('cursor-pointer')
    })
  })

  // ==========================================================================
  // Accessibility Tests
  // ==========================================================================

  describe('Accessibility', () => {
    it('hat korrektes table role auf Desktop', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('table')).toBeInTheDocument()
    })

    it('hat korrektes row role auf Desktop', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('row')).toBeInTheDocument()
    })

    it('hat korrektes cell role auf Desktop', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>Cell</ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('cell')).toBeInTheDocument()
    })
  })

  // ==========================================================================
  // Edge Cases
  // ==========================================================================

  describe('Edge Cases', () => {
    it('behandelt leere Tabelle graceful', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('table')).toBeInTheDocument()
    })

    it('behandelt Zellen ohne Content', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell></ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByRole('cell')).toBeInTheDocument()
    })

    it('behandelt komplexen Cell-Content', () => {
      render(
        <ResponsiveTable>
          <ResponsiveTableBody>
            <ResponsiveTableRow>
              <ResponsiveTableCell>
                <div>
                  <span>Nested</span>
                  <button>Button</button>
                </div>
              </ResponsiveTableCell>
            </ResponsiveTableRow>
          </ResponsiveTableBody>
        </ResponsiveTable>
      )

      expect(screen.getByText('Nested')).toBeInTheDocument()
      expect(screen.getByRole('button')).toBeInTheDocument()
    })
  })
})
