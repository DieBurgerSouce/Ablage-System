/**
 * BWAPage
 *
 * BWA (Business Report) overview page
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Plus, FileText, ArrowLeft, BarChart3 } from 'lucide-react';
import { BWAReportView, BWAComparisonChart } from '../components';
import { useBWAReports, useBWAReport, useGenerateBWAReport, useBWAComparison } from '../hooks/use-german-finance-queries';
import { UI_LABELS } from '../types/german-finance-types';
import type { BWAReport } from '../types/german-finance-types';

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatPeriod = (year: number, month: number): string => {
  const monthNames = [
    'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
    'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
  ];
  return `${monthNames[month - 1]} ${year}`;
};

export function BWAPage() {
  const currentYear = new Date().getFullYear();
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [compareReportId1, setCompareReportId1] = useState<string | null>(null);
  const [compareReportId2, setCompareReportId2] = useState<string | null>(null);
  const [showGenerateForm, setShowGenerateForm] = useState(false);
  const [generateYear, setGenerateYear] = useState(currentYear);
  const [generateMonth, setGenerateMonth] = useState(new Date().getMonth() + 1);
  const [generateSchema, setGenerateSchema] = useState<'skr03' | 'skr04'>('skr03');

  const { data: reports, isLoading } = useBWAReports();
  const { data: selectedReport } = useBWAReport(selectedReportId || '', {
    enabled: !!selectedReportId,
  });
  const { data: comparisonData } = useBWAComparison(
    compareReportId1 || '',
    compareReportId2 || '',
  );

  const generateMutation = useGenerateBWAReport();

  const handleGenerate = async () => {
    try {
      await generateMutation.mutateAsync({
        year: generateYear,
        month: generateMonth,
        schema: generateSchema,
      });
      setShowGenerateForm(false);
    } catch (error) {
      console.error('Failed to generate BWA:', error);
    }
  };

  // View Mode: Single Report
  if (selectedReportId && selectedReport) {
    return (
      <div className="container mx-auto space-y-6 py-8">
        <Button
          variant="ghost"
          onClick={() => setSelectedReportId(null)}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurück zur Übersicht
        </Button>
        <BWAReportView
          report={selectedReport}
          onPrint={() => window.print()}
        />
      </div>
    );
  }

  // View Mode: Comparison
  if (compareReportId1 && compareReportId2 && comparisonData) {
    return (
      <div className="container mx-auto space-y-6 py-8">
        <Button
          variant="ghost"
          onClick={() => {
            setCompareReportId1(null);
            setCompareReportId2(null);
          }}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurück zur Übersicht
        </Button>
        <BWAComparisonChart data={comparisonData} />
      </div>
    );
  }

  // Main View: List
  return (
    <div className="container mx-auto space-y-6 py-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{UI_LABELS.bwa.title}</h1>
        <p className="text-muted-foreground">{UI_LABELS.bwa.subtitle}</p>
      </div>

      {/* Generate Form */}
      {showGenerateForm && (
        <Card>
          <CardHeader>
            <CardTitle>{UI_LABELS.bwa.generate}</CardTitle>
            <CardDescription>
              Erstellen Sie eine neue BWA für einen bestimmten Zeitraum
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <Label htmlFor="generate-year">{UI_LABELS.common.year}</Label>
                <Input
                  id="generate-year"
                  type="number"
                  value={generateYear}
                  onChange={(e) => setGenerateYear(Number(e.target.value))}
                  min={2020}
                  max={2030}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="generate-month">{UI_LABELS.common.month}</Label>
                <Select
                  value={generateMonth.toString()}
                  onValueChange={(val) => setGenerateMonth(Number(val))}
                >
                  <SelectTrigger id="generate-month">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
                      <SelectItem key={month} value={month.toString()}>
                        {new Date(2000, month - 1).toLocaleDateString('de-DE', { month: 'long' })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="generate-schema">{UI_LABELS.bwa.schema}</Label>
                <Select
                  value={generateSchema}
                  onValueChange={(val) => setGenerateSchema(val as 'skr03' | 'skr04')}
                >
                  <SelectTrigger id="generate-schema">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skr03">SKR03</SelectItem>
                    <SelectItem value="skr04">SKR04</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end gap-2">
                <Button
                  onClick={handleGenerate}
                  disabled={generateMutation.isPending}
                  className="flex-1"
                >
                  {generateMutation.isPending ? 'Erstellt...' : 'Erstellen'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setShowGenerateForm(false)}
                >
                  {UI_LABELS.common.cancel}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Reports List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>BWA-Berichte</CardTitle>
              <CardDescription>Übersicht aller erstellten BWA-Berichte</CardDescription>
            </div>
            <div className="flex gap-2">
              {!showGenerateForm && (
                <Button onClick={() => setShowGenerateForm(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  {UI_LABELS.bwa.generate}
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : !reports || reports.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              {UI_LABELS.common.noData}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Zeitraum</TableHead>
                  <TableHead>Schema</TableHead>
                  <TableHead className="text-right">Erlöse</TableHead>
                  <TableHead className="text-right">Ergebnis</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[150px]">{UI_LABELS.common.actions}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((report) => (
                  <TableRow key={report.id}>
                    <TableCell className="font-medium">
                      {formatPeriod(report.year, report.month)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono">
                        {report.schema.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium text-green-600">
                      {formatEuro(report.revenue)}
                    </TableCell>
                    <TableCell
                      className={`text-right font-medium ${
                        report.profit >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {formatEuro(report.profit)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={report.status === 'final' ? 'default' : 'secondary'}>
                        {UI_LABELS.bwa.status[report.status]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedReportId(report.id)}
                        >
                          <FileText className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (!compareReportId1) {
                              setCompareReportId1(report.id);
                            } else {
                              setCompareReportId2(report.id);
                            }
                          }}
                          disabled={
                            compareReportId1 === report.id ||
                            compareReportId2 === report.id
                          }
                        >
                          <BarChart3 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Comparison Selection */}
          {(compareReportId1 || compareReportId2) && (
            <div className="mt-4 flex items-center justify-between rounded-lg border bg-muted/50 p-4">
              <div className="text-sm">
                <span className="font-medium">Vergleichsmodus:</span>
                {compareReportId1 && <Badge className="ml-2">Bericht 1 ausgewählt</Badge>}
                {compareReportId2 && <Badge className="ml-2">Bericht 2 ausgewählt</Badge>}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setCompareReportId1(null);
                  setCompareReportId2(null);
                }}
              >
                Abbrechen
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
