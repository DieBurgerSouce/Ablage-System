/**
 * Widget Export Button Component
 *
 * Dropdown button for exporting dashboard widgets:
 * - PNG export (image)
 * - PDF export (document)
 * - CSV export (data)
 * - Copy to clipboard
 *
 * Phase 3.3 Feature 13: Dashboard Widget Export
 */

import { useCallback, useRef } from 'react';
import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    Download,
    Image,
    FileText,
    Table,
    Copy,
    Loader2,
} from 'lucide-react';
import { useWidgetExport, type ExportOptions } from '../hooks/useWidgetExport';

// =============================================================================
// Types
// =============================================================================

export interface WidgetExportButtonProps {
    /** Reference to the widget element to export */
    widgetRef: React.RefObject<HTMLElement>;
    /** Widget title for filename */
    widgetTitle?: string;
    /** Widget data for CSV export */
    widgetData?: Record<string, unknown>[];
    /** Show as icon-only button */
    iconOnly?: boolean;
    /** Additional className */
    className?: string;
    /** Disable the button */
    disabled?: boolean;
    /** Custom export options */
    exportOptions?: ExportOptions;
    /** Callback after successful export */
    onExportComplete?: (format: string) => void;
}

// =============================================================================
// Component
// =============================================================================

export function WidgetExportButton({
    widgetRef,
    widgetTitle = 'widget',
    widgetData,
    iconOnly = true,
    className,
    disabled = false,
    exportOptions = {},
    onExportComplete,
}: WidgetExportButtonProps) {
    const {
        isExporting,
        exportWidgetToPng,
        exportDashboardToPdf,
        exportWidgetDataToCsv,
        copyWidgetToClipboard,
    } = useWidgetExport();

    // Sanitize filename
    const sanitizedTitle = widgetTitle
        .toLowerCase()
        .replace(/[^a-z0-9äöüß]/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');

    const handlePngExport = useCallback(async () => {
        if (!widgetRef.current) return;
        const result = await exportWidgetToPng(widgetRef.current, {
            filename: sanitizedTitle,
            ...exportOptions,
        });
        if (result.success) {
            onExportComplete?.('png');
        }
    }, [widgetRef, sanitizedTitle, exportOptions, exportWidgetToPng, onExportComplete]);

    const handlePdfExport = useCallback(async () => {
        if (!widgetRef.current) return;
        const result = await exportDashboardToPdf(widgetRef.current, {
            filename: sanitizedTitle,
            ...exportOptions,
        });
        if (result.success) {
            onExportComplete?.('pdf');
        }
    }, [widgetRef, sanitizedTitle, exportOptions, exportDashboardToPdf, onExportComplete]);

    const handleCsvExport = useCallback(async () => {
        if (!widgetData || widgetData.length === 0) return;
        const result = await exportWidgetDataToCsv(widgetData, {
            filename: sanitizedTitle,
            ...exportOptions,
        });
        if (result.success) {
            onExportComplete?.('csv');
        }
    }, [widgetData, sanitizedTitle, exportOptions, exportWidgetDataToCsv, onExportComplete]);

    const handleCopyToClipboard = useCallback(async () => {
        if (!widgetRef.current) return;
        const success = await copyWidgetToClipboard(widgetRef.current);
        if (success) {
            onExportComplete?.('clipboard');
        }
    }, [widgetRef, copyWidgetToClipboard, onExportComplete]);

    const buttonContent = isExporting ? (
        <Loader2 className="h-4 w-4 animate-spin" />
    ) : (
        <Download className="h-4 w-4" />
    );

    return (
        <DropdownMenu>
            <TooltipProvider>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <DropdownMenuTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className={className}
                                disabled={disabled || isExporting}
                                aria-label="Widget exportieren"
                            >
                                {buttonContent}
                            </Button>
                        </DropdownMenuTrigger>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p>Widget exportieren</p>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>

            <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel>Export</DropdownMenuLabel>
                <DropdownMenuSeparator />

                <DropdownMenuItem
                    onClick={handlePngExport}
                    disabled={isExporting}
                >
                    <Image className="h-4 w-4 mr-2" />
                    Als Bild (PNG)
                </DropdownMenuItem>

                <DropdownMenuItem
                    onClick={handlePdfExport}
                    disabled={isExporting}
                >
                    <FileText className="h-4 w-4 mr-2" />
                    Als PDF
                </DropdownMenuItem>

                {widgetData && widgetData.length > 0 && (
                    <DropdownMenuItem
                        onClick={handleCsvExport}
                        disabled={isExporting}
                    >
                        <Table className="h-4 w-4 mr-2" />
                        Als CSV (Daten)
                    </DropdownMenuItem>
                )}

                <DropdownMenuSeparator />

                <DropdownMenuItem
                    onClick={handleCopyToClipboard}
                    disabled={isExporting}
                >
                    <Copy className="h-4 w-4 mr-2" />
                    In Zwischenablage
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

// =============================================================================
// Dashboard Export Button
// =============================================================================

export interface DashboardExportButtonProps {
    /** Reference to the dashboard container */
    dashboardRef: React.RefObject<HTMLElement>;
    /** Dashboard title for filename */
    title?: string;
    /** Additional className */
    className?: string;
    /** Callback after successful export */
    onExportComplete?: (format: string) => void;
}

export function DashboardExportButton({
    dashboardRef,
    title = 'dashboard',
    className,
    onExportComplete,
}: DashboardExportButtonProps) {
    const { isExporting, exportDashboardToPdf, exportWidgetToPng } = useWidgetExport();

    const sanitizedTitle = title
        .toLowerCase()
        .replace(/[^a-z0-9äöüß]/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');

    const handlePdfExport = useCallback(async () => {
        if (!dashboardRef.current) return;
        const result = await exportDashboardToPdf(dashboardRef.current, {
            filename: sanitizedTitle,
        });
        if (result.success) {
            onExportComplete?.('pdf');
        }
    }, [dashboardRef, sanitizedTitle, exportDashboardToPdf, onExportComplete]);

    const handlePngExport = useCallback(async () => {
        if (!dashboardRef.current) return;
        const result = await exportWidgetToPng(dashboardRef.current, {
            filename: sanitizedTitle,
            scale: 1.5, // Lower scale for full dashboard
        });
        if (result.success) {
            onExportComplete?.('png');
        }
    }, [dashboardRef, sanitizedTitle, exportWidgetToPng, onExportComplete]);

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="outline"
                    size="sm"
                    className={className}
                    disabled={isExporting}
                >
                    {isExporting ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                        <Download className="h-4 w-4 mr-2" />
                    )}
                    Exportieren
                </Button>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>Dashboard exportieren</DropdownMenuLabel>
                <DropdownMenuSeparator />

                <DropdownMenuItem
                    onClick={handlePdfExport}
                    disabled={isExporting}
                >
                    <FileText className="h-4 w-4 mr-2" />
                    Als PDF herunterladen
                </DropdownMenuItem>

                <DropdownMenuItem
                    onClick={handlePngExport}
                    disabled={isExporting}
                >
                    <Image className="h-4 w-4 mr-2" />
                    Als Bild herunterladen
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

export default WidgetExportButton;
