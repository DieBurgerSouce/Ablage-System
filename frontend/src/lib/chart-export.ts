/**
 * Chart Export Utilities
 *
 * Exportiert Charts und Visualisierungen als PNG, JPEG oder SVG.
 * Unterstuetzt Recharts, native SVG und Canvas-basierte Charts.
 */

import { toPng, toJpeg, toSvg, toBlob } from 'html-to-image'

// =============================================================================
// Types
// =============================================================================

export type ExportFormat = 'png' | 'jpeg' | 'svg'

export interface ExportOptions {
  /** File name without extension */
  fileName?: string
  /** Export format */
  format?: ExportFormat
  /** Background color (default: white) */
  backgroundColor?: string
  /** Image quality for JPEG (0-1, default: 0.95) */
  quality?: number
  /** Scale factor for higher resolution (default: 2) */
  scale?: number
  /** Include timestamp in filename */
  includeTimestamp?: boolean
  /** Custom width (optional) */
  width?: number
  /** Custom height (optional) */
  height?: number
  /** Filter function for elements */
  filter?: (node: HTMLElement) => boolean
}

export interface ExportResult {
  success: boolean
  fileName?: string
  error?: string
  dataUrl?: string
}

// =============================================================================
// Core Export Functions
// =============================================================================

/**
 * Export a DOM element to an image
 */
export async function exportElement(
  element: HTMLElement,
  options: ExportOptions = {}
): Promise<ExportResult> {
  const {
    fileName = 'chart',
    format = 'png',
    backgroundColor = '#ffffff',
    quality = 0.95,
    scale = 2,
    includeTimestamp = true,
    width,
    height,
    filter,
  } = options

  try {
    // Build filename
    const timestamp = includeTimestamp
      ? `_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}`
      : ''
    const fullFileName = `${fileName}${timestamp}.${format}`

    const exportOptions = {
      backgroundColor,
      quality,
      pixelRatio: scale,
      width,
      height,
      filter,
      cacheBust: true,
      style: {
        // Ensure chart renders properly
        transform: 'scale(1)',
        transformOrigin: 'top left',
      },
    }

    let dataUrl: string

    switch (format) {
      case 'png':
        dataUrl = await toPng(element, exportOptions)
        break
      case 'jpeg':
        dataUrl = await toJpeg(element, exportOptions)
        break
      case 'svg':
        dataUrl = await toSvg(element, exportOptions)
        break
      default:
        throw new Error(`Nicht unterstütztes Format: ${format}`)
    }

    // Download file
    downloadDataUrl(dataUrl, fullFileName)

    return {
      success: true,
      fileName: fullFileName,
      dataUrl,
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Export fehlgeschlagen'

    return {
      success: false,
      error: errorMessage,
    }
  }
}

/**
 * Export a chart by ref
 */
export async function exportChartByRef(
  chartRef: React.RefObject<HTMLElement>,
  options: ExportOptions = {}
): Promise<ExportResult> {
  if (!chartRef.current) {
    return {
      success: false,
      error: 'Chart-Referenz nicht gefunden',
    }
  }

  return exportElement(chartRef.current, options)
}

/**
 * Export a chart by ID
 */
export async function exportChartById(
  chartId: string,
  options: ExportOptions = {}
): Promise<ExportResult> {
  const element = document.getElementById(chartId)
  if (!element) {
    return {
      success: false,
      error: `Element mit ID "${chartId}" nicht gefunden`,
    }
  }

  return exportElement(element as HTMLElement, options)
}

/**
 * Export all charts on the page
 */
export async function exportAllCharts(
  containerSelector: string = '[data-chart]',
  options: ExportOptions = {}
): Promise<ExportResult[]> {
  const charts = document.querySelectorAll<HTMLElement>(containerSelector)
  const results: ExportResult[] = []

  for (let i = 0; i < charts.length; i++) {
    const chart = charts[i]
    const chartName = chart.getAttribute('data-chart-name') || `chart_${i + 1}`

    const result = await exportElement(chart, {
      ...options,
      fileName: chartName,
    })
    results.push(result)
  }

  return results
}

// =============================================================================
// Download Helpers
// =============================================================================

/**
 * Download a data URL as a file
 */
function downloadDataUrl(dataUrl: string, fileName: string): void {
  const link = document.createElement('a')
  link.download = fileName
  link.href = dataUrl
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/**
 * Download a blob as a file
 */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.download = fileName
  link.href = url
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * Convert data URL to blob
 * @throws Error if dataUrl is invalid
 */
export function dataUrlToBlob(dataUrl: string): Blob {
  if (!dataUrl || typeof dataUrl !== 'string') {
    throw new Error('Ungültige Data-URL: Eingabe ist leer oder kein String')
  }

  if (!dataUrl.startsWith('data:')) {
    throw new Error('Ungültige Data-URL: Muss mit "data:" beginnen')
  }

  const commaIndex = dataUrl.indexOf(',')
  if (commaIndex === -1) {
    throw new Error('Ungültige Data-URL: Kein Komma-Separator gefunden')
  }

  const header = dataUrl.slice(0, commaIndex)
  const data = dataUrl.slice(commaIndex + 1)

  if (!data) {
    throw new Error('Ungültige Data-URL: Keine Daten nach dem Separator')
  }

  const mimeMatch = header.match(/:(.*?);/)
  const mime = mimeMatch ? mimeMatch[1] : 'image/png'

  let binary: string
  try {
    binary = atob(data)
  } catch {
    throw new Error('Ungültige Data-URL: Base64-Dekodierung fehlgeschlagen')
  }

  const array = new Uint8Array(binary.length)

  for (let i = 0; i < binary.length; i++) {
    array[i] = binary.charCodeAt(i)
  }

  return new Blob([array], { type: mime })
}

// =============================================================================
// Clipboard Functions
// =============================================================================

export interface CopyToClipboardResult {
  success: boolean
  error?: string
}

/**
 * Copy chart to clipboard
 * Returns result object with success status and optional error message
 */
export async function copyChartToClipboard(
  element: HTMLElement,
  options: Omit<ExportOptions, 'format' | 'fileName'> = {}
): Promise<CopyToClipboardResult> {
  try {
    const blob = await toBlob(element, {
      backgroundColor: options.backgroundColor || '#ffffff',
      pixelRatio: options.scale || 2,
      cacheBust: true,
    })

    if (!blob) {
      return {
        success: false,
        error: 'Bild konnte nicht erstellt werden',
      }
    }

    await navigator.clipboard.write([
      new ClipboardItem({
        [blob.type]: blob,
      }),
    ])

    return { success: true }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Kopieren in Zwischenablage fehlgeschlagen'
    return {
      success: false,
      error: errorMessage,
    }
  }
}

// =============================================================================
// React Hook
// =============================================================================

import { useCallback, useRef, useState } from 'react'

export interface UseChartExportReturn<T extends HTMLElement> {
  /** Ref to attach to chart container */
  chartRef: React.RefObject<T>
  /** Export the chart */
  exportChart: (options?: ExportOptions) => Promise<ExportResult>
  /** Copy chart to clipboard */
  copyToClipboard: () => Promise<CopyToClipboardResult>
  /** Export is in progress */
  isExporting: boolean
  /** Last export result */
  lastResult: ExportResult | null
}

/**
 * Hook for chart export functionality
 *
 * @example
 * ```tsx
 * function MyChart() {
 *   const { chartRef, exportChart, isExporting } = useChartExport<HTMLDivElement>()
 *
 *   return (
 *     <div>
 *       <div ref={chartRef}>
 *         <BarChart data={data} />
 *       </div>
 *       <Button
 *         onClick={() => exportChart({ fileName: 'umsatz-chart', format: 'png' })}
 *         disabled={isExporting}
 *       >
 *         Als PNG exportieren
 *       </Button>
 *     </div>
 *   )
 * }
 * ```
 */
export function useChartExport<T extends HTMLElement = HTMLDivElement>(): UseChartExportReturn<T> {
  const chartRef = useRef<T>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [lastResult, setLastResult] = useState<ExportResult | null>(null)
  // Guard against concurrent export operations
  const exportInProgressRef = useRef(false)

  const exportChart = useCallback(async (options: ExportOptions = {}): Promise<ExportResult> => {
    // Prevent concurrent exports - return last result if already exporting
    if (exportInProgressRef.current) {
      return lastResult ?? {
        success: false,
        error: 'Export bereits in Bearbeitung',
      }
    }

    if (!chartRef.current) {
      const result: ExportResult = {
        success: false,
        error: 'Chart-Referenz nicht gefunden',
      }
      setLastResult(result)
      return result
    }

    exportInProgressRef.current = true
    setIsExporting(true)
    try {
      const result = await exportElement(chartRef.current, options)
      setLastResult(result)
      return result
    } finally {
      exportInProgressRef.current = false
      setIsExporting(false)
    }
  }, [lastResult])

  const copyToClipboard = useCallback(async (): Promise<CopyToClipboardResult> => {
    // Prevent concurrent operations
    if (exportInProgressRef.current) {
      return { success: false, error: 'Export bereits in Bearbeitung' }
    }

    if (!chartRef.current) {
      return { success: false, error: 'Chart-Referenz nicht gefunden' }
    }

    exportInProgressRef.current = true
    setIsExporting(true)
    try {
      return await copyChartToClipboard(chartRef.current)
    } finally {
      exportInProgressRef.current = false
      setIsExporting(false)
    }
  }, [])

  return {
    chartRef,
    exportChart,
    copyToClipboard,
    isExporting,
    lastResult,
  }
}

// =============================================================================
// Export Button Component
// =============================================================================

import type { ReactNode } from 'react'

export interface ChartExportButtonProps {
  /** Element to export */
  elementRef: React.RefObject<HTMLElement>
  /** Export options */
  options?: ExportOptions
  /** Children (button content) */
  children?: ReactNode
  /** Custom class name */
  className?: string
  /** Disabled state */
  disabled?: boolean
  /** Called on export start */
  onExportStart?: () => void
  /** Called on export complete */
  onExportComplete?: (result: ExportResult) => void
}

// Note: The actual Button component should be imported from @/components/ui/button
// This is just the interface for the export button props
