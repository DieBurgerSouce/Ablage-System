/**
 * XlsxViewer - Excel Spreadsheet Viewer
 *
 * Rendert XLSX-Dateien im Browser mithilfe von SheetJS (xlsx).
 * Zeigt Tabellen mit Sheets, Zeilen und Spalten an.
 */

import { useState, useEffect, useMemo } from 'react';
import * as XLSX from 'xlsx';
import { Loader2, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { logger } from '@/lib/logger';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface XlsxViewerProps {
    /** Blob URL or ArrayBuffer of the XLSX file */
    fileData: ArrayBuffer | Blob | string;
    /** Optional CSS class name */
    className?: string;
}

interface SheetData {
    name: string;
    data: string[][];
    merges?: XLSX.Range[];
    isTruncated?: boolean;
    originalRowCount?: number;
}

// ==================== Constants ====================

/** Maximum file size in bytes (10 MB) */
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

/** Maximum rows to render without virtualization */
const MAX_ROWS_DISPLAY = 1000;

/** Warning threshold for large files */
const LARGE_FILE_ROW_THRESHOLD = 500;

// ==================== Helper Functions ====================

/**
 * Escape HTML entities to prevent XSS
 */
function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.textContent || '';
}

/**
 * Convert column index to Excel-style letter (0 = A, 1 = B, etc.)
 */
function columnIndexToLetter(index: number): string {
    let result = '';
    let n = index;
    while (n >= 0) {
        result = String.fromCharCode((n % 26) + 65) + result;
        n = Math.floor(n / 26) - 1;
    }
    return result;
}

// ==================== Component ====================

export function XlsxViewer({ fileData, className }: XlsxViewerProps) {
    const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
    const [sheets, setSheets] = useState<SheetData[]>([]);
    const [activeSheet, setActiveSheet] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Parse XLSX file
    useEffect(() => {
        let cancelled = false;

        async function parseSpreadsheet() {
            setIsLoading(true);
            setError(null);

            try {
                let arrayBuffer: ArrayBuffer;

                if (fileData instanceof ArrayBuffer) {
                    arrayBuffer = fileData;
                } else if (fileData instanceof Blob) {
                    // Check file size before loading
                    if (fileData.size > MAX_FILE_SIZE_BYTES) {
                        throw new Error(
                            `Datei zu gross (${(fileData.size / 1024 / 1024).toFixed(1)} MB). ` +
                            `Maximal ${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB erlaubt.`
                        );
                    }
                    arrayBuffer = await fileData.arrayBuffer();
                } else if (typeof fileData === 'string') {
                    const response = await fetch(fileData);
                    const contentLength = response.headers.get('content-length');
                    if (contentLength && parseInt(contentLength, 10) > MAX_FILE_SIZE_BYTES) {
                        throw new Error(
                            `Datei zu gross. Maximal ${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB erlaubt.`
                        );
                    }
                    arrayBuffer = await response.arrayBuffer();
                } else {
                    throw new Error('Ungültiges Dateiformat');
                }

                // Verify size of loaded buffer
                if (arrayBuffer.byteLength > MAX_FILE_SIZE_BYTES) {
                    throw new Error(
                        `Datei zu gross (${(arrayBuffer.byteLength / 1024 / 1024).toFixed(1)} MB). ` +
                        `Maximal ${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB erlaubt.`
                    );
                }

                if (cancelled) return;

                const wb = XLSX.read(arrayBuffer, {
                    type: 'array',
                    cellStyles: true,
                    cellDates: true,
                });

                if (cancelled) return;

                // Convert each sheet to array data
                const sheetDataList: SheetData[] = wb.SheetNames.map((name) => {
                    const sheet = wb.Sheets[name];
                    const jsonData = XLSX.utils.sheet_to_json<string[]>(sheet, {
                        header: 1,
                        defval: '',
                        blankrows: true,
                    });

                    // Truncate large sheets to prevent DOM overload
                    const originalRowCount = jsonData.length;
                    const isTruncated = originalRowCount > MAX_ROWS_DISPLAY;
                    const displayData = isTruncated
                        ? jsonData.slice(0, MAX_ROWS_DISPLAY)
                        : jsonData;

                    return {
                        name,
                        data: displayData,
                        merges: sheet['!merges'],
                        isTruncated,
                        originalRowCount,
                    };
                });

                setWorkbook(wb);
                setSheets(sheetDataList);
                setActiveSheet(0);
            } catch (err) {
                if (cancelled) return;
                const message = err instanceof Error
                    ? err.message
                    : 'Tabelle konnte nicht geladen werden';
                setError(message);
                logger.error('Fehler beim Parsen der Tabelle', err);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        }

        parseSpreadsheet();

        return () => {
            cancelled = true;
        };
    }, [fileData]);

    // Get current sheet data
    const currentSheet = sheets[activeSheet];

    // Calculate max columns (handle empty arrays to prevent Math.max(...[]) crash)
    const maxColumns = useMemo(() => {
        if (!currentSheet || currentSheet.data.length === 0) return 0;
        const lengths = currentSheet.data.map((row) => row.length);
        // Math.max(...[]) throws TypeError - need at least one value
        return lengths.length > 0 ? Math.max(...lengths) : 0;
    }, [currentSheet]);

    // Navigate sheets
    const handlePrevSheet = () => setActiveSheet((i) => Math.max(0, i - 1));
    const handleNextSheet = () => setActiveSheet((i) => Math.min(sheets.length - 1, i + 1));

    if (isLoading) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <span>Lade Tabelle...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-destructive">
                    <AlertTriangle className="h-8 w-8" />
                    <span>Tabelle konnte nicht geladen werden</span>
                    <span className="text-xs text-muted-foreground">{error}</span>
                </div>
            </div>
        );
    }

    if (!currentSheet || sheets.length === 0) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <span className="text-muted-foreground">Keine Daten vorhanden</span>
            </div>
        );
    }

    return (
        <div className={cn('h-full flex flex-col', className)}>
            {/* Sheet Tabs */}
            {sheets.length > 1 && (
                <div className="flex items-center gap-2 px-4 py-2 border-b bg-background/95 backdrop-blur">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handlePrevSheet}
                        disabled={activeSheet === 0}
                    >
                        <ChevronLeft className="h-4 w-4" />
                    </Button>

                    <Tabs
                        value={String(activeSheet)}
                        onValueChange={(v) => setActiveSheet(Number(v))}
                        className="flex-1"
                    >
                        <TabsList className="h-auto p-1 flex-wrap justify-start">
                            {sheets.map((sheet, index) => (
                                <TabsTrigger
                                    key={sheet.name}
                                    value={String(index)}
                                    className="text-xs px-3 py-1"
                                >
                                    {sheet.name}
                                </TabsTrigger>
                            ))}
                        </TabsList>
                    </Tabs>

                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleNextSheet}
                        disabled={activeSheet === sheets.length - 1}
                    >
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                </div>
            )}

            {/* Truncation Warning */}
            {currentSheet.isTruncated && (
                <div className="px-4 py-2 border-b text-xs bg-amber-500/10 text-amber-700 dark:text-amber-400 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" />
                    <span>
                        Grosse Tabelle: Es werden nur die ersten {MAX_ROWS_DISPLAY} von{' '}
                        {currentSheet.originalRowCount?.toLocaleString('de-DE')} Zeilen angezeigt.
                        Laden Sie die Datei herunter, um alle Daten zu sehen.
                    </span>
                </div>
            )}

            {/* Sheet Info */}
            <div className="px-4 py-2 border-b text-xs text-muted-foreground bg-muted/30">
                {currentSheet.isTruncated ? (
                    <>
                        {currentSheet.data.length} von {currentSheet.originalRowCount?.toLocaleString('de-DE')} Zeilen, {maxColumns} Spalten
                    </>
                ) : (
                    <>
                        {currentSheet.data.length} Zeilen, {maxColumns} Spalten
                    </>
                )}
                {sheets.length > 1 && (
                    <span className="ml-2">
                        (Blatt {activeSheet + 1} von {sheets.length})
                    </span>
                )}
            </div>

            {/* Table Content */}
            <ScrollArea className="flex-1">
                <div className="p-4">
                    <table className="xlsx-table w-full border-collapse text-sm">
                        <thead>
                            <tr>
                                {/* Row number header */}
                                <th className="xlsx-header-cell sticky left-0 z-20 bg-muted border px-2 py-1 text-center font-medium w-12">
                                    #
                                </th>
                                {/* Column headers (A, B, C, ...) */}
                                {Array.from({ length: maxColumns }).map((_, colIdx) => (
                                    <th
                                        key={colIdx}
                                        className="xlsx-header-cell sticky top-0 z-10 bg-muted border px-2 py-1 text-center font-medium min-w-[80px]"
                                    >
                                        {columnIndexToLetter(colIdx)}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {currentSheet.data.map((row, rowIdx) => (
                                <tr key={rowIdx} className="hover:bg-muted/50">
                                    {/* Row number */}
                                    <td className="xlsx-row-number sticky left-0 z-10 bg-muted border px-2 py-1 text-center text-muted-foreground font-mono text-xs">
                                        {rowIdx + 1}
                                    </td>
                                    {/* Data cells */}
                                    {Array.from({ length: maxColumns }).map((_, colIdx) => {
                                        const cellValue = row[colIdx];
                                        const displayValue = cellValue != null
                                            ? String(cellValue)
                                            : '';

                                        return (
                                            <td
                                                key={colIdx}
                                                className="xlsx-cell border px-2 py-1 whitespace-nowrap"
                                                title={displayValue}
                                            >
                                                {escapeHtml(displayValue)}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                <ScrollBar orientation="horizontal" />
            </ScrollArea>

            {/* Embedded styles for XLSX table */}
            <style>{`
                .xlsx-table {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .xlsx-header-cell {
                    background: hsl(var(--muted));
                    color: hsl(var(--muted-foreground));
                }
                .xlsx-row-number {
                    background: hsl(var(--muted));
                }
                .xlsx-cell {
                    max-width: 300px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .xlsx-cell:hover {
                    max-width: none;
                    overflow: visible;
                    position: relative;
                    z-index: 5;
                    background: hsl(var(--background));
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                }
            `}</style>
        </div>
    );
}

export default XlsxViewer;
