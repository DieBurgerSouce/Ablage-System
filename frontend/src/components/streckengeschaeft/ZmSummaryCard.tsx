/**
 * ZM Summary Component
 *
 * Displays the Zusammenfassende Meldung (EC Sales List) summary
 * for triangular and intra-community transactions.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLanguage } from '@/lib/i18n/useLanguage';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Globe,
  Calendar,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Clock,
  TrendingUp,
  Building2,
} from 'lucide-react';

import type { ZmSummary, ZmRecord } from '@/types/streckengeschaeft';
import { apiClient } from '@/lib/api/client';

// =============================================================================
// PERIOD SELECTOR
// =============================================================================

function PeriodSelector({
  value,
  onChange,
  t,
}: {
  value: string;
  onChange: (period: string) => void;
  t: (key: string) => string;
}) {
  const now = new Date();
  const periods: string[] = [];

  // Generate last 12 months
  for (let i = 0; i < 12; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
    periods.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`);
  }

  const formatPeriod = (period: string) => {
    const [year, month] = period.split('-');
    const monthName = t(`streckengeschaeft.zm.months.${parseInt(month)}`);
    return `${monthName} ${year}`;
  };

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-[200px]">
        <SelectValue placeholder={t('streckengeschaeft.zm.period')} />
      </SelectTrigger>
      <SelectContent>
        {periods.map((period) => (
          <SelectItem key={period} value={period}>
            {formatPeriod(period)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// =============================================================================
// DEADLINE INDICATOR
// =============================================================================

function DeadlineIndicator({
  deadline,
  isSubmitted,
  language,
  t,
}: {
  deadline: string;
  isSubmitted: boolean;
  language: 'de' | 'en';
  t: (key: string, params?: Record<string, unknown>) => string;
}) {
  const deadlineDate = new Date(deadline);
  const now = new Date();
  const daysRemaining = Math.ceil(
    (deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  );

  if (isSubmitted) {
    return (
      <Badge variant="default" className="bg-success">
        <CheckCircle2 className="h-3 w-3 mr-1" aria-hidden="true" />
        {t('streckengeschaeft.zmCard.submitted')}
      </Badge>
    );
  }

  if (daysRemaining < 0) {
    return (
      <Badge variant="destructive">
        <AlertTriangle className="h-3 w-3 mr-1" aria-hidden="true" />
        {t('streckengeschaeft.zmCard.overdue', { days: Math.abs(daysRemaining) })}
      </Badge>
    );
  }

  if (daysRemaining <= 5) {
    return (
      <Badge variant="destructive">
        <Clock className="h-3 w-3 mr-1" />
        {t('streckengeschaeft.zmCard.daysRemaining', { days: daysRemaining })}
      </Badge>
    );
  }

  if (daysRemaining <= 14) {
    return (
      <Badge variant="secondary">
        <Clock className="h-3 w-3 mr-1" />
        {t('streckengeschaeft.zmCard.daysRemaining', { days: daysRemaining })}
      </Badge>
    );
  }

  return (
    <Badge variant="outline">
      <Calendar className="h-3 w-3 mr-1" />
      {t('streckengeschaeft.zmCard.deadline')}{' '}
      {deadlineDate.toLocaleDateString(language === 'de' ? 'de-DE' : 'en-US')}
    </Badge>
  );
}

// =============================================================================
// COUNTRY BREAKDOWN
// =============================================================================

function CountryBreakdown({
  byCountry,
  language,
  t,
}: {
  byCountry: Array<{ countryCode: string; amount: number; recordCount: number }>;
  language: 'de' | 'en';
  t: (key: string, params?: Record<string, unknown>) => string;
}) {
  const total = byCountry.reduce((sum, c) => sum + c.amount, 0);

  return (
    <div className="space-y-3">
      {byCountry.map((country) => {
        const percentage = total > 0 ? (country.amount / total) * 100 : 0;

        return (
          <div key={country.countryCode} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{country.countryCode}</Badge>
                <span className="text-muted-foreground">
                  {country.recordCount} {t('streckengeschaeft.zmCard.records')}
                </span>
              </div>
              <span className="font-medium">
                {country.amount.toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                  style: 'currency',
                  currency: 'EUR',
                })}
              </span>
            </div>
            <Progress value={percentage} className="h-2" />
          </div>
        );
      })}
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function ZmSummaryCard() {
  const { t, language } = useLanguage();
  const now = new Date();
  const currentPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const [selectedPeriod, setSelectedPeriod] = useState(currentPeriod);

  const {
    data: summary,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['streckengeschaeft', 'zm', 'summary', selectedPeriod],
    queryFn: async () => {
      const response = await apiClient.get<ZmSummary>(`/streckengeschäft/zm/summary`, {
        params: { period: selectedPeriod },
      });
      return response.data;
    },
  });

  const { data: records } = useQuery({
    queryKey: ['streckengeschaeft', 'zm', 'records', selectedPeriod],
    queryFn: async () => {
      const response = await apiClient.get(`/streckengeschäft/zm/records`, {
        params: { period: selectedPeriod },
      });
      return response.data;
    },
    enabled: !!summary,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="pt-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{t('common.error')}</AlertTitle>
            <AlertDescription>
              {t('streckengeschaeft.zmCard.loadError')}
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              {t('streckengeschaeft.zm.title')}
            </CardTitle>
            <CardDescription>{t('streckengeschaeft.zm.subtitle')}</CardDescription>
          </div>
          <PeriodSelector value={selectedPeriod} onChange={setSelectedPeriod} t={t} />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {summary ? (
          <>
            {/* Status and Deadline */}
            <div className="flex items-center justify-between">
              <DeadlineIndicator
                deadline={summary.deadline}
                isSubmitted={summary.isSubmitted}
                language={language}
                t={t}
              />
              {summary.submittedAt && (
                <span className="text-sm text-muted-foreground">
                  {t('streckengeschaeft.zmCard.submittedOn')}{' '}
                  {new Date(summary.submittedAt).toLocaleDateString(
                    language === 'de' ? 'de-DE' : 'en-US'
                  )}
                </span>
              )}
            </div>

            {/* Summary Stats */}
            <div className="grid gap-4 md:grid-cols-3">
              <div className="p-4 border rounded-lg">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <TrendingUp className="h-4 w-4" />
                  {t('streckengeschaeft.zm.totalAmount')}
                </div>
                <p className="text-2xl font-bold">
                  {summary.totalAmount.toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                    style: 'currency',
                    currency: 'EUR',
                  })}
                </p>
              </div>
              <div className="p-4 border rounded-lg">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <Building2 className="h-4 w-4" />
                  {t('streckengeschaeft.zm.triangularCount')}
                </div>
                <p className="text-2xl font-bold">
                  {summary.triangularAmount.toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                    style: 'currency',
                    currency: 'EUR',
                  })}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t('streckengeschaeft.zmCard.triangularMarker')}
                </p>
              </div>
              <div className="p-4 border rounded-lg">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <FileText className="h-4 w-4" />
                  {t('streckengeschaeft.zm.recordCount')}
                </div>
                <p className="text-2xl font-bold">{summary.recordCount}</p>
                <p className="text-xs text-muted-foreground">
                  {summary.triangularRecordCount}{' '}
                  {t('streckengeschaeft.zmCard.triangularTransactions')}
                </p>
              </div>
            </div>

            {/* Country Breakdown */}
            {summary.byCountry && summary.byCountry.length > 0 && (
              <div>
                <h4 className="font-medium mb-3">
                  {t('streckengeschaeft.zmCard.byCountry')}
                </h4>
                <CountryBreakdown byCountry={summary.byCountry} language={language} t={t} />
              </div>
            )}

            {/* Records Table */}
            {records?.records && records.records.length > 0 && (
              <div>
                <h4 className="font-medium mb-3">
                  {t('streckengeschaeft.zmCard.individualRecords')}
                </h4>
                <div className="border rounded-lg max-h-64 overflow-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>
                          {t('streckengeschaeft.zmCard.vatId')}
                        </TableHead>
                        <TableHead>{t('streckengeschaeft.zmCard.country')}</TableHead>
                        <TableHead className="text-right">
                          {t('streckengeschaeft.detail.amount')}
                        </TableHead>
                        <TableHead>{t('streckengeschaeft.zmCard.marker')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {records.records.slice(0, 10).map((record: ZmRecord, i: number) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono text-sm">{record.vatId}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{record.countryCode}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            {record.amount.toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                              style: 'currency',
                              currency: 'EUR',
                            })}
                          </TableCell>
                          <TableCell>
                            {record.triangularMarker === '1' && <Badge>Kz.1</Badge>}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {records.records.length > 10 && (
                  <p className="text-sm text-muted-foreground mt-2 text-center">
                    ... {t('streckengeschaeft.zmCard.moreRecords', { count: records.records.length - 10 })}
                  </p>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-4 border-t">
              <Button variant="outline">
                <Download className="h-4 w-4 mr-2" />
                {t('streckengeschaeft.zm.exportElster')}
              </Button>
              <Button variant="outline">
                <FileText className="h-4 w-4 mr-2" />
                CSV {t('common.export')}
              </Button>
              {!summary.isSubmitted && (
                <Button className="ml-auto">
                  <CheckCircle2 className="h-4 w-4 mr-2" />
                  {t('streckengeschaeft.zmCard.markSubmitted')}
                </Button>
              )}
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Globe className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>
              {t('streckengeschaeft.zmCard.noTransactions')}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default ZmSummaryCard;
