// Analytics Page Component
// Main page with tab navigation, time filter, and tab-specific content

import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, Download, FileText } from 'lucide-react';
import { toast } from 'sonner';
import {
  AnalyticsTabBar,
  TimeRangeFilter,
  OperationsTab,
  FinanceTab,
  TeamTab,
} from '../components';
import { useInvalidateAnalytics } from '../hooks/use-analytics-queries';
import { analyticsApi } from '../api/analytics-api';
import {
  type AnalyticsTabKey,
  type AnalyticsPeriod,
  type CustomDateRange,
  PERIOD_OPTIONS,
  UI_LABELS,
} from '../types/analytics-types';

export function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<AnalyticsTabKey>('betrieb');
  const [period, setPeriod] = useState<AnalyticsPeriod>('monat');
  const [customRange, setCustomRange] = useState<CustomDateRange>({
    startDate: '',
    endDate: '',
  });
  const [isExporting, setIsExporting] = useState(false);
  const [isExportingPDF, setIsExportingPDF] = useState(false);
  const invalidateAnalytics = useInvalidateAnalytics();

  const handleExportCSV = useCallback(async () => {
    setIsExporting(true);
    try {
      const apiPeriod = PERIOD_OPTIONS.find((o) => o.value === period)?.apiValue ?? 'month';
      const exportRange = period === 'custom' ? customRange : undefined;
      const blob = await analyticsApi.exportCSV(activeTab, apiPeriod, exportRange);

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const suffix = period === 'custom' && customRange.startDate
        ? `${customRange.startDate}_${customRange.endDate}`
        : period;
      a.download = `analytics-${activeTab}-${suffix}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success('CSV erfolgreich exportiert');
    } catch {
      toast.error('Export fehlgeschlagen');
    } finally {
      setIsExporting(false);
    }
  }, [activeTab, period, customRange]);

  const handleExportPDF = useCallback(async () => {
    setIsExportingPDF(true);
    try {
      const apiPeriod = PERIOD_OPTIONS.find((o) => o.value === period)?.apiValue ?? 'month';
      const exportRange = period === 'custom' ? customRange : undefined;
      const blob = await analyticsApi.exportPDF(activeTab, apiPeriod, exportRange);

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const suffix = period === 'custom' && customRange.startDate
        ? `${customRange.startDate}_${customRange.endDate}`
        : period;
      a.download = `analytics-${activeTab}-${suffix}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast.success('PDF erfolgreich exportiert');
    } catch {
      toast.error('PDF-Export fehlgeschlagen');
    } finally {
      setIsExportingPDF(false);
    }
  }, [activeTab, period, customRange]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {UI_LABELS.PAGE_TITLE}
          </h1>
          <p className="text-muted-foreground">{UI_LABELS.PAGE_SUBTITLE}</p>
        </div>
        <div className="flex items-center gap-2">
          <TimeRangeFilter
            value={period}
            onChange={setPeriod}
            customRange={customRange}
            onCustomRangeChange={setCustomRange}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportCSV}
            disabled={isExporting}
          >
            <Download className={`mr-2 h-4 w-4 ${isExporting ? 'animate-pulse' : ''}`} />
            {UI_LABELS.ACTION_EXPORT_CSV}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPDF}
            disabled={isExportingPDF}
          >
            <FileText className={`mr-2 h-4 w-4 ${isExportingPDF ? 'animate-pulse' : ''}`} />
            {UI_LABELS.ACTION_EXPORT_PDF}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={invalidateAnalytics}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            {UI_LABELS.ACTION_REFRESH}
          </Button>
        </div>
      </div>

      {/* Tab Navigation */}
      <AnalyticsTabBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab Content */}
      <div className="mt-4">
        {activeTab === 'betrieb' && <OperationsTab period={period} />}
        {activeTab === 'finanzen' && <FinanceTab period={period} />}
        {activeTab === 'team' && <TeamTab period={period} />}
      </div>
    </div>
  );
}
