/**
 * Chart Export Button Component
 *
 * Dropdown-Button zum Exportieren von Charts in verschiedenen Formaten.
 */

import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Download, Copy, Image, FileImage, FileCode, Check, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import {
  exportElement,
  copyChartToClipboard,
  type ExportOptions,
  type ExportResult,
  type ExportFormat,
} from '@/lib/chart-export'

// =============================================================================
// Types
// =============================================================================

interface ChartExportButtonProps {
  /** Reference to the chart element to export */
  elementRef: React.RefObject<HTMLElement>
  /** Base filename for exports */
  fileName?: string
  /** Available export formats */
  formats?: ExportFormat[]
  /** Show copy to clipboard option */
  showCopyOption?: boolean
  /** Custom export options */
  exportOptions?: Omit<ExportOptions, 'format' | 'fileName'>
  /** Called on export start */
  onExportStart?: () => void
  /** Called on export complete */
  onExportComplete?: (result: ExportResult) => void
  /** Custom button variant */
  variant?: 'default' | 'outline' | 'ghost' | 'secondary'
  /** Custom button size */
  size?: 'default' | 'sm' | 'lg' | 'icon'
  /** Disabled state */
  disabled?: boolean
  /** Custom children */
  children?: ReactNode
  /** Custom class name */
  className?: string
}

// =============================================================================
// Component
// =============================================================================

export function ChartExportButton({
  elementRef,
  fileName = 'chart',
  formats = ['png', 'jpeg', 'svg'],
  showCopyOption = true,
  exportOptions = {},
  onExportStart,
  onExportComplete,
  variant = 'outline',
  size = 'sm',
  disabled = false,
  children,
  className,
}: ChartExportButtonProps) {
  const [isExporting, setIsExporting] = useState(false)
  const [copiedToClipboard, setCopiedToClipboard] = useState(false)
  const copiedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Cleanup timeout on unmount to prevent memory leak
  useEffect(() => {
    return () => {
      if (copiedTimeoutRef.current) {
        clearTimeout(copiedTimeoutRef.current)
      }
    }
  }, [])

  const formatLabels: Record<ExportFormat, { label: string; icon: ReactNode }> = {
    png: { label: 'Als PNG', icon: <Image className="h-4 w-4 mr-2" /> },
    jpeg: { label: 'Als JPEG', icon: <FileImage className="h-4 w-4 mr-2" /> },
    svg: { label: 'Als SVG', icon: <FileCode className="h-4 w-4 mr-2" /> },
  }

  const handleExport = async (format: ExportFormat) => {
    if (!elementRef.current) {
      toast.error('Chart nicht gefunden')
      return
    }

    setIsExporting(true)
    onExportStart?.()

    try {
      const result = await exportElement(elementRef.current, {
        ...exportOptions,
        format,
        fileName,
      })

      if (result.success) {
        toast.success(`Chart als ${format.toUpperCase()} exportiert`, {
          description: result.fileName,
        })
      } else {
        toast.error('Export fehlgeschlagen', {
          description: result.error,
        })
      }

      onExportComplete?.(result)
    } finally {
      setIsExporting(false)
    }
  }

  const handleCopyToClipboard = async () => {
    if (!elementRef.current) {
      toast.error('Chart nicht gefunden')
      return
    }

    setIsExporting(true)

    try {
      const result = await copyChartToClipboard(elementRef.current, exportOptions)

      if (result.success) {
        setCopiedToClipboard(true)
        toast.success('Chart in Zwischenablage kopiert')
        // Clear previous timeout if exists
        if (copiedTimeoutRef.current) {
          clearTimeout(copiedTimeoutRef.current)
        }
        copiedTimeoutRef.current = setTimeout(() => setCopiedToClipboard(false), 2000)
      } else {
        toast.error('Kopieren fehlgeschlagen', {
          description: result.error,
        })
      }
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={variant}
          size={size}
          disabled={disabled || isExporting}
          className={className}
          aria-label="Chart exportieren"
        >
          {isExporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            children || (
              <>
                <Download className="h-4 w-4 mr-2" />
                Exportieren
              </>
            )
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {formats.map((format) => (
          <DropdownMenuItem
            key={format}
            onClick={() => handleExport(format)}
            disabled={isExporting}
          >
            {formatLabels[format].icon}
            {formatLabels[format].label}
          </DropdownMenuItem>
        ))}

        {showCopyOption && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleCopyToClipboard} disabled={isExporting}>
              {copiedToClipboard ? (
                <Check className="h-4 w-4 mr-2 text-green-500" />
              ) : (
                <Copy className="h-4 w-4 mr-2" />
              )}
              In Zwischenablage kopieren
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// =============================================================================
// Simple Export Button (no dropdown)
// =============================================================================

interface SimpleChartExportButtonProps {
  /** Reference to the chart element to export */
  elementRef: React.RefObject<HTMLElement>
  /** Export format */
  format?: ExportFormat
  /** Base filename */
  fileName?: string
  /** Export options */
  exportOptions?: Omit<ExportOptions, 'format' | 'fileName'>
  /** Button variant */
  variant?: 'default' | 'outline' | 'ghost' | 'secondary'
  /** Button size */
  size?: 'default' | 'sm' | 'lg' | 'icon'
  /** Custom children */
  children?: ReactNode
  /** Custom class name */
  className?: string
}

export function SimpleChartExportButton({
  elementRef,
  format = 'png',
  fileName = 'chart',
  exportOptions = {},
  variant = 'outline',
  size = 'sm',
  children,
  className,
}: SimpleChartExportButtonProps) {
  const [isExporting, setIsExporting] = useState(false)

  const handleExport = async () => {
    if (!elementRef.current) {
      toast.error('Chart nicht gefunden')
      return
    }

    setIsExporting(true)

    try {
      const result = await exportElement(elementRef.current, {
        ...exportOptions,
        format,
        fileName,
      })

      if (result.success) {
        toast.success(`Chart als ${format.toUpperCase()} exportiert`)
      } else {
        toast.error('Export fehlgeschlagen', { description: result.error })
      }
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleExport}
      disabled={isExporting}
      className={className}
      aria-label={`Chart als ${format.toUpperCase()} exportieren`}
    >
      {isExporting ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        children || (
          <>
            <Download className="h-4 w-4 mr-2" />
            {format.toUpperCase()}
          </>
        )
      )}
    </Button>
  )
}
