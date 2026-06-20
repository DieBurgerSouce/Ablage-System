/**
 * Widget Export Hook
 *
 * Provides functionality to export dashboard widgets:
 * - PNG export per widget (html2canvas)
 * - PDF export of entire dashboard
 * - Scheduled report support
 *
 * Phase 3.3 Feature 13: Dashboard Widget Export
 */

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

// =============================================================================
// Types
// =============================================================================

export type ExportFormat = 'png' | 'pdf' | 'csv';

export interface ExportOptions {
    /** Export file name (without extension) */
    filename?: string;
    /** Quality for image exports (0-1, default: 1) */
    quality?: number;
    /** Scale factor for higher resolution (default: 2) */
    scale?: number;
    /** Background color (default: white) */
    backgroundColor?: string;
    /** Include timestamp in filename */
    includeTimestamp?: boolean;
    /** Custom width for export */
    width?: number;
    /** Custom height for export */
    height?: number;
}

export interface ExportResult {
    success: boolean;
    filename?: string;
    error?: string;
    blob?: Blob;
    dataUrl?: string;
}

export interface UseWidgetExportReturn {
    /** Whether export is in progress */
    isExporting: boolean;
    /** Last export error */
    error: string | null;
    /** Export a single widget to PNG */
    exportWidgetToPng: (
        element: HTMLElement,
        options?: ExportOptions
    ) => Promise<ExportResult>;
    /** Export entire dashboard to PDF */
    exportDashboardToPdf: (
        container: HTMLElement,
        options?: ExportOptions
    ) => Promise<ExportResult>;
    /** Export widget data to CSV */
    exportWidgetDataToCsv: (
        data: Record<string, unknown>[],
        options?: ExportOptions
    ) => Promise<ExportResult>;
    /** Copy widget as image to clipboard */
    copyWidgetToClipboard: (element: HTMLElement) => Promise<boolean>;
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Generate filename with optional timestamp
 */
function generateFilename(
    baseName: string,
    extension: string,
    includeTimestamp = true
): string {
    if (includeTimestamp) {
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');
        return `${baseName}_${timestamp}.${extension}`;
    }
    return `${baseName}.${extension}`;
}

/**
 * Download a blob as file
 */
function downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Convert canvas to blob
 */
async function canvasToBlob(
    canvas: HTMLCanvasElement,
    type: string,
    quality: number
): Promise<Blob> {
    return new Promise((resolve, reject) => {
        canvas.toBlob(
            (blob) => {
                if (blob) {
                    resolve(blob);
                } else {
                    reject(new Error('Canvas toBlob fehlgeschlagen'));
                }
            },
            type,
            quality
        );
    });
}

/**
 * Dynamically import html2canvas
 */
async function getHtml2Canvas() {
    try {
        const module = await import('html2canvas');
        return module.default;
    } catch {
        throw new Error(
            'html2canvas konnte nicht geladen werden. Bitte installieren Sie das Paket.'
        );
    }
}

/**
 * Dynamically import jsPDF
 */
async function getJsPdf() {
    try {
        const module = await import('jspdf');
        return module.default;
    } catch {
        throw new Error(
            'jsPDF konnte nicht geladen werden. Bitte installieren Sie das Paket.'
        );
    }
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useWidgetExport(): UseWidgetExportReturn {
    const [isExporting, setIsExporting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    /**
     * Export a single widget to PNG
     */
    const exportWidgetToPng = useCallback(
        async (
            element: HTMLElement,
            options: ExportOptions = {}
        ): Promise<ExportResult> => {
            const {
                filename = 'widget',
                quality = 1,
                scale = 2,
                backgroundColor = '#ffffff',
                includeTimestamp = true,
            } = options;

            setIsExporting(true);
            setError(null);

            try {
                const html2canvas = await getHtml2Canvas();

                const canvas = await html2canvas(element, {
                    scale,
                    backgroundColor,
                    logging: false,
                    useCORS: true,
                    allowTaint: true,
                });

                const blob = await canvasToBlob(canvas, 'image/png', quality);
                const exportFilename = generateFilename(filename, 'png', includeTimestamp);

                downloadBlob(blob, exportFilename);

                toast.success('Widget exportiert', {
                    description: `${exportFilename} wurde heruntergeladen.`,
                });

                return {
                    success: true,
                    filename: exportFilename,
                    blob,
                    dataUrl: canvas.toDataURL('image/png', quality),
                };
            } catch (err) {
                const errorMessage =
                    err instanceof Error ? err.message : 'Export fehlgeschlagen';
                setError(errorMessage);
                toast.error('Export fehlgeschlagen', {
                    description: errorMessage,
                });
                return {
                    success: false,
                    error: errorMessage,
                };
            } finally {
                setIsExporting(false);
            }
        },
        []
    );

    /**
     * Export entire dashboard to PDF
     */
    const exportDashboardToPdf = useCallback(
        async (
            container: HTMLElement,
            options: ExportOptions = {}
        ): Promise<ExportResult> => {
            const {
                filename = 'dashboard',
                scale = 2,
                backgroundColor = '#ffffff',
                includeTimestamp = true,
            } = options;

            setIsExporting(true);
            setError(null);

            try {
                const [html2canvas, jsPDF] = await Promise.all([
                    getHtml2Canvas(),
                    getJsPdf(),
                ]);

                // Capture the container
                const canvas = await html2canvas(container, {
                    scale,
                    backgroundColor,
                    logging: false,
                    useCORS: true,
                    allowTaint: true,
                    windowWidth: container.scrollWidth,
                    windowHeight: container.scrollHeight,
                });

                // Calculate PDF dimensions (A4 landscape for dashboards)
                const imgWidth = 297; // A4 landscape width in mm
                const imgHeight = (canvas.height * imgWidth) / canvas.width;

                // Create PDF
                const pdf = new jsPDF({
                    orientation: imgHeight > imgWidth ? 'portrait' : 'landscape',
                    unit: 'mm',
                    format: 'a4',
                });

                // Add image to PDF
                const imgData = canvas.toDataURL('image/jpeg', 0.95);

                // Handle multi-page if content is too tall
                const pageHeight = pdf.internal.pageSize.getHeight();
                let heightLeft = imgHeight;
                let position = 0;

                pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight);
                heightLeft -= pageHeight;

                while (heightLeft > 0) {
                    position = heightLeft - imgHeight;
                    pdf.addPage();
                    pdf.addImage(imgData, 'JPEG', 0, position, imgWidth, imgHeight);
                    heightLeft -= pageHeight;
                }

                // Save PDF
                const exportFilename = generateFilename(filename, 'pdf', includeTimestamp);
                pdf.save(exportFilename);

                toast.success('Dashboard exportiert', {
                    description: `${exportFilename} wurde heruntergeladen.`,
                });

                return {
                    success: true,
                    filename: exportFilename,
                };
            } catch (err) {
                const errorMessage =
                    err instanceof Error ? err.message : 'PDF-Export fehlgeschlagen';
                setError(errorMessage);
                toast.error('Export fehlgeschlagen', {
                    description: errorMessage,
                });
                return {
                    success: false,
                    error: errorMessage,
                };
            } finally {
                setIsExporting(false);
            }
        },
        []
    );

    /**
     * Export widget data to CSV
     */
    const exportWidgetDataToCsv = useCallback(
        async (
            data: Record<string, unknown>[],
            options: ExportOptions = {}
        ): Promise<ExportResult> => {
            const { filename = 'widget-data', includeTimestamp = true } = options;

            setIsExporting(true);
            setError(null);

            try {
                if (!data || data.length === 0) {
                    throw new Error('Keine Daten zum Exportieren vorhanden');
                }

                // Get headers from first row
                const headers = Object.keys(data[0]);

                // Build CSV content
                const csvRows = [
                    headers.join(';'), // German uses semicolon as delimiter
                    ...data.map((row) =>
                        headers
                            .map((header) => {
                                const value = row[header];
                                // Escape quotes and wrap in quotes if contains special chars
                                const stringValue = String(value ?? '');
                                if (
                                    stringValue.includes(';') ||
                                    stringValue.includes('"') ||
                                    stringValue.includes('\n')
                                ) {
                                    return `"${stringValue.replace(/"/g, '""')}"`;
                                }
                                return stringValue;
                            })
                            .join(';')
                    ),
                ];

                // Add BOM for Excel UTF-8 compatibility
                const BOM = '\uFEFF';
                const csvContent = BOM + csvRows.join('\n');

                const blob = new Blob([csvContent], {
                    type: 'text/csv;charset=utf-8',
                });
                const exportFilename = generateFilename(filename, 'csv', includeTimestamp);

                downloadBlob(blob, exportFilename);

                toast.success('Daten exportiert', {
                    description: `${exportFilename} wurde heruntergeladen.`,
                });

                return {
                    success: true,
                    filename: exportFilename,
                    blob,
                };
            } catch (err) {
                const errorMessage =
                    err instanceof Error ? err.message : 'CSV-Export fehlgeschlagen';
                setError(errorMessage);
                toast.error('Export fehlgeschlagen', {
                    description: errorMessage,
                });
                return {
                    success: false,
                    error: errorMessage,
                };
            } finally {
                setIsExporting(false);
            }
        },
        []
    );

    /**
     * Copy widget as image to clipboard
     */
    const copyWidgetToClipboard = useCallback(
        async (element: HTMLElement): Promise<boolean> => {
            setIsExporting(true);
            setError(null);

            try {
                const html2canvas = await getHtml2Canvas();

                const canvas = await html2canvas(element, {
                    scale: 2,
                    backgroundColor: '#ffffff',
                    logging: false,
                    useCORS: true,
                });

                const blob = await canvasToBlob(canvas, 'image/png', 1);

                await navigator.clipboard.write([
                    new ClipboardItem({
                        'image/png': blob,
                    }),
                ]);

                toast.success('In Zwischenablage kopiert', {
                    description: 'Das Widget wurde als Bild kopiert.',
                });

                return true;
            } catch (err) {
                const errorMessage =
                    err instanceof Error
                        ? err.message
                        : 'Kopieren fehlgeschlagen';
                setError(errorMessage);
                toast.error('Kopieren fehlgeschlagen', {
                    description: errorMessage,
                });
                return false;
            } finally {
                setIsExporting(false);
            }
        },
        []
    );

    return {
        isExporting,
        error,
        exportWidgetToPng,
        exportDashboardToPdf,
        exportWidgetDataToCsv,
        copyWidgetToClipboard,
    };
}

export default useWidgetExport;
