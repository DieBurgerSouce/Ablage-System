/**
 * UStReportList Component
 *
 * List of USt-Voranmeldung reports
 */

import { useState } from 'react';
import { logger } from '@/lib/logger';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
import { Skeleton } from '@/components/ui/skeleton';
import { FileText, Plus } from 'lucide-react';
import { useUStReports, useGenerateUStReport } from '../hooks/use-german-finance-queries';
import type { UStReport } from '../types/german-finance-types';
import { UI_LABELS } from '../types/german-finance-types';

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
};

const formatPeriod = (year: number, month: number): string => {
  const monthNames = [
    'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
    'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'
  ];
  return `${monthNames[month - 1]} ${year}`;
};

const getStatusVariant = (status: UStReport['status']): 'default' | 'secondary' | 'outline' => {
  switch (status) {
    case 'approved':
      return 'default';
    case 'submitted':
      return 'secondary';
    case 'draft':
    default:
      return 'outline';
  }
};

interface UStReportListProps {
  onViewReport?: (reportId: string) => void;
}

export function UStReportList({ onViewReport }: UStReportListProps) {
  const currentYear = new Date().getFullYear();
  const [filterYear, setFilterYear] = useState<number | undefined>(currentYear);
  const [filterStatus, setFilterStatus] = useState<'all' | 'draft' | 'submitted' | 'approved'>('all');
  const [showGenerateForm, setShowGenerateForm] = useState(false);
  const [generateYear, setGenerateYear] = useState(currentYear);
  const [generateMonth, setGenerateMonth] = useState(new Date().getMonth() + 1);

  const { data: reports, isLoading } = useUStReports({
    year: filterYear,
    status: filterStatus === 'all' ? undefined : filterStatus,
  });

  const generateMutation = useGenerateUStReport();

  const handleGenerate = async () => {
    try {
      await generateMutation.mutateAsync({
        year: generateYear,
        month: generateMonth,
        include_corrections: true,
      });
      setShowGenerateForm(false);
    } catch (error) {
      logger.error('Failed to generate USt report:', error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Generate Form */}
      {showGenerateForm && (
        <Card>
          <CardHeader>
            <CardTitle>{UI_LABELS.ust.generate}</CardTitle>
            <CardDescription>
              Erstellen Sie eine neue USt-Voranmeldung für einen bestimmten Zeitraum
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
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
              <CardTitle>{UI_LABELS.ust.title}</CardTitle>
              <CardDescription>{UI_LABELS.ust.subtitle}</CardDescription>
            </div>
            {!showGenerateForm && (
              <Button onClick={() => setShowGenerateForm(true)}>
                <Plus className="mr-2 h-4 w-4" />
                {UI_LABELS.ust.generate}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {/* Filters */}
          <div className="mb-6 flex gap-4">
            <div className="w-32">
              <Select
                value={filterYear?.toString() || 'all'}
                onValueChange={(val) => setFilterYear(val === 'all' ? undefined : Number(val))}
              >
                <SelectTrigger>
                  <SelectValue placeholder={UI_LABELS.common.year} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Jahre</SelectItem>
                  {Array.from({ length: 5 }, (_, i) => currentYear - i).map((year) => (
                    <SelectItem key={year} value={year.toString()}>
                      {year}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="w-40">
              <Select
                value={filterStatus}
                onValueChange={(val) => setFilterStatus(val as typeof filterStatus)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Alle Status</SelectItem>
                  <SelectItem value="draft">Entwurf</SelectItem>
                  <SelectItem value="submitted">Eingereicht</SelectItem>
                  <SelectItem value="approved">Genehmigt</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Table */}
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
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Zahllast</TableHead>
                  <TableHead className="text-right">Erstellt</TableHead>
                  <TableHead className="w-[100px]">{UI_LABELS.common.actions}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((report) => (
                  <TableRow key={report.id}>
                    <TableCell className="font-medium">
                      {formatPeriod(report.year, report.month)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(report.status)}>
                        {UI_LABELS.ust.status[report.status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatEuro(report.zahllast)}
                    </TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">
                      {report.createdAt.toLocaleDateString('de-DE')}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onViewReport?.(report.id)}
                      >
                        <FileText className="mr-2 h-4 w-4" />
                        Ansehen
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
