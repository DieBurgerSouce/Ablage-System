/**
 * DATEVExportButton Component
 *
 * Button zum Generieren und Herunterladen eines DATEV-kompatiblen Exports.
 * Zeigt Vorschau der Export-Daten und ermoeglicht Download.
 */

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Download,
  FileSpreadsheet,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Info,
  ExternalLink,
} from 'lucide-react';
import { useDATEVExport, useDATEVExportDownload } from '../hooks';
import type { DATEVExportData } from '@/lib/api/services/tax-optimization';

// ==================== Props ====================

interface DATEVExportButtonProps {
  spaceId: string;
  taxYear?: number;
  datevExportReady?: boolean;
  datevExportNotes?: string;
}

// ==================== Hilfsfunktionen ====================

const formatCurrency = (value: string): string => {
  const num = parseFloat(value);
  return num.toLocaleString('de-DE', {
    style: 'currency',
    currency: 'EUR',
  });
};

// ==================== Component ====================

export function DATEVExportButton({
  spaceId,
  taxYear: propTaxYear,
  datevExportReady = true,
  datevExportNotes,
}: DATEVExportButtonProps) {
  const currentYear = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = React.useState<number>(propTaxYear || currentYear);
  const [exportData, setExportData] = React.useState<DATEVExportData | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);

  const exportMutation = useDATEVExport();
  const downloadMutation = useDATEVExportDownload();

  // Verfuegbare Jahre (aktuelle und letzte 5)
  const availableYears = React.useMemo(() => {
    const years: number[] = [];
    for (let i = 0; i < 6; i++) {
      years.push(currentYear - i);
    }
    return years;
  }, [currentYear]);

  const handleGenerateExport = async () => {
    try {
      const data = await exportMutation.mutateAsync({
        spaceId,
        taxYear: selectedYear,
      });
      setExportData(data);
    } catch {
      // Fehler wird durch Mutation behandelt
    }
  };

  const handleDownload = async () => {
    try {
      await downloadMutation.mutateAsync({
        spaceId,
        taxYear: selectedYear,
      });
    } catch {
      // Fehler wird durch Mutation behandelt
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    setExportData(null);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="gap-2">
          <FileSpreadsheet className="h-4 w-4" />
          DATEV-Export
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            DATEV-Export generieren
          </DialogTitle>
          <DialogDescription>
            Exportieren Sie Ihre Steuerabzuege im DATEV-kompatiblen Format
            fuer Ihren Steuerberater.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Jahr-Auswahl */}
          <div className="space-y-2">
            <Label>Steuerjahr</Label>
            <Select
              value={String(selectedYear)}
              onValueChange={(v) => {
                setSelectedYear(parseInt(v, 10));
                setExportData(null);
              }}
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableYears.map((year) => (
                  <SelectItem key={year} value={String(year)}>
                    {year}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Export-Status Warnung */}
          {!datevExportReady && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Export nicht bereit</AlertTitle>
              <AlertDescription>
                {datevExportNotes || 'Bitte verifizieren Sie alle Belege vor dem Export.'}
              </AlertDescription>
            </Alert>
          )}

          {/* Export-Vorschau */}
          {exportData ? (
            <div className="space-y-4">
              <Alert>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <AlertTitle className="text-green-600">Export generiert</AlertTitle>
                <AlertDescription>
                  Format: {exportData.formatVersion} | Erstellt: {
                    new Date(exportData.exportDate).toLocaleDateString('de-DE', {
                      day: '2-digit',
                      month: '2-digit',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }
                </AlertDescription>
              </Alert>

              <div className="border rounded-lg">
                <div className="p-3 bg-muted/50 border-b flex justify-between items-center">
                  <span className="font-medium">Export-Inhalt</span>
                  <Badge variant="secondary">
                    Gesamt: {formatCurrency(exportData.totalDeductible)}
                  </Badge>
                </div>
                <ScrollArea className="h-[250px]">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Kategorie</TableHead>
                        <TableHead className="text-right">Brutto</TableHead>
                        <TableHead className="text-right">Absetzbar</TableHead>
                        <TableHead>Konten</TableHead>
                        <TableHead className="text-right">Belege</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {exportData.categories.map((cat) => (
                        <TableRow key={cat.category}>
                          <TableCell className="font-medium">{cat.categoryName}</TableCell>
                          <TableCell className="text-right">
                            {formatCurrency(cat.totalGross)}
                          </TableCell>
                          <TableCell className="text-right text-green-600">
                            {formatCurrency(cat.totalDeductible)}
                          </TableCell>
                          <TableCell>
                            {cat.suggestedAccounts.map((acc) => (
                              <Badge
                                key={acc.konto}
                                variant="outline"
                                className="mr-1 text-xs"
                              >
                                {acc.konto}
                              </Badge>
                            ))}
                          </TableCell>
                          <TableCell className="text-right">{cat.itemCount}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </div>

              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>SKR03 Kontenrahmen</AlertTitle>
                <AlertDescription>
                  Die vorgeschlagenen Konten basieren auf dem Standardkontenrahmen SKR03.
                  Ihr Steuerberater kann diese bei Bedarf anpassen.
                </AlertDescription>
              </Alert>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <FileSpreadsheet className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Klicken Sie auf "Vorschau generieren", um den Export zu erstellen.</p>
            </div>
          )}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="ghost" onClick={handleClose}>
            Schliessen
          </Button>
          {!exportData ? (
            <Button
              onClick={handleGenerateExport}
              disabled={exportMutation.isPending || !datevExportReady}
            >
              {exportMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generiere...
                </>
              ) : (
                <>
                  <FileSpreadsheet className="h-4 w-4 mr-2" />
                  Vorschau generieren
                </>
              )}
            </Button>
          ) : (
            <Button
              onClick={handleDownload}
              disabled={downloadMutation.isPending}
              className="bg-green-600 hover:bg-green-700"
            >
              {downloadMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Lade herunter...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4 mr-2" />
                  CSV herunterladen
                </>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default DATEVExportButton;
