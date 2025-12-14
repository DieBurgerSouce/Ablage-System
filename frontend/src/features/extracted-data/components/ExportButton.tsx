/**
 * ExportButton - Dropdown für CSV/Excel-Export.
 *
 * Zeigt Export-Optionen basierend auf dem Dokumenttyp.
 */

import { useState } from "react";
import { Download, FileSpreadsheet, FileDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { extractedDataApi } from "../api/extracted-data-api";
import type { ExtractedDocumentType } from "../types/extracted-data.types";

interface ExportButtonProps {
    documentType?: ExtractedDocumentType;
    className?: string;
}

// Dokumenttyp zu deutschen Dateinamen
const DOCUMENT_TYPE_FILENAMES: Record<string, string> = {
    invoice: "rechnungen",
    order: "bestellungen",
    contract: "vertraege",
};

export function ExportButton({ documentType = "invoice", className }: ExportButtonProps) {
    const [isExporting, setIsExporting] = useState(false);

    const handleExportCsv = async () => {
        setIsExporting(true);
        try {
            const url = extractedDataApi.getExportCsvUrl({ document_type: documentType });
            const filename = `${DOCUMENT_TYPE_FILENAMES[documentType] || "export"}_${new Date().toISOString().slice(0, 10)}.csv`;
            await extractedDataApi.downloadExport(url, filename);
        } catch (error) {
            console.error("CSV Export fehlgeschlagen:", error);
        } finally {
            setIsExporting(false);
        }
    };

    const handleExportExcel = async () => {
        setIsExporting(true);
        try {
            const url = extractedDataApi.getExportExcelUrl({ document_type: documentType });
            const filename = `${DOCUMENT_TYPE_FILENAMES[documentType] || "export"}_${new Date().toISOString().slice(0, 10)}.xlsx`;
            await extractedDataApi.downloadExport(url, filename);
        } catch (error) {
            console.error("Excel Export fehlgeschlagen:", error);
        } finally {
            setIsExporting(false);
        }
    };

    const handleExportAll = async () => {
        setIsExporting(true);
        try {
            const url = extractedDataApi.getExportAllExcelUrl();
            const filename = `alle_dokumente_${new Date().toISOString().slice(0, 10)}.xlsx`;
            await extractedDataApi.downloadExport(url, filename);
        } catch (error) {
            console.error("Gesamt-Export fehlgeschlagen:", error);
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className={className} disabled={isExporting}>
                    {isExporting ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                        <Download className="h-4 w-4 mr-2" />
                    )}
                    Export
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleExportCsv}>
                    <FileDown className="h-4 w-4 mr-2" />
                    Als CSV exportieren
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleExportExcel}>
                    <FileSpreadsheet className="h-4 w-4 mr-2" />
                    Als Excel exportieren
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleExportAll}>
                    <FileSpreadsheet className="h-4 w-4 mr-2" />
                    Alle Dokumenttypen (Excel)
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
