// Analytics Dashboard API Service
// Aggregates data from multiple existing endpoints + new team stats endpoint

import { apiClient } from '@/lib/api/client';
import type {
  BackendOperationsData,
  BackendFinanceData,
  BackendTeamStats,
  BackendWorkloadData,
  AnalyticsTabKey,
  CustomDateRange,
} from '../types/analytics-types';

// ============================================================================
// ERROR MESSAGES (German)
// ============================================================================

const ERROR_MESSAGES = {
  FETCH_OPERATIONS_FAILED: 'Fehler beim Laden der Betriebsdaten',
  FETCH_FINANCE_FAILED: 'Fehler beim Laden der Finanzdaten',
  FETCH_TEAM_FAILED: 'Fehler beim Laden der Team-Statistiken',
  FETCH_WORKLOAD_FAILED: 'Fehler beim Laden der Workload-Daten',
  EXPORT_FAILED: 'Fehler beim Erstellen des Exports',
} as const;

// ============================================================================
// HELPERS
// ============================================================================

function buildDateParams(
  period: string,
  customRange?: CustomDateRange,
): Record<string, string> {
  if (customRange?.startDate && customRange?.endDate) {
    return {
      start_date: customRange.startDate,
      end_date: customRange.endDate,
    };
  }
  return { period };
}

// ============================================================================
// API SERVICE
// ============================================================================

export const analyticsApi = {
  /**
   * Aggregates CEO Dashboard + Smart Dashboard data for operations metrics
   */
  async getOperationsData(period: string, customRange?: CustomDateRange): Promise<BackendOperationsData> {
    try {
      const params = buildDateParams(period, customRange);
      // Fetch from CEO dashboard overview + smart dashboard KPIs in parallel
      const [overviewRes, kpisRes] = await Promise.all([
        apiClient.get('/ceo-dashboard/overview', { params }),
        apiClient.get('/smart-dashboard/kpis', { params }),
      ]);

      const overview = overviewRes.data;
      const kpis = kpisRes.data;

      // Find specific KPIs from smart-dashboard
      const findKpi = (key: string) => {
        const kpi = Array.isArray(kpis) ? kpis.find((k: { key: string }) => k.key === key) : null;
        return kpi?.value ?? 0;
      };

      return {
        documents_processed: {
          today: overview.document_stats?.today ?? findKpi('documents_today') ?? 0,
          week: overview.document_stats?.week ?? 0,
          month: overview.document_stats?.month ?? 0,
        },
        ocr_accuracy_percent: overview.ocr_accuracy ?? 0,
        ocr_accuracy_trend: overview.ocr_accuracy_trend ?? 'neutral',
        pending_approvals: findKpi('pending_approvals'),
        oldest_approval_days: overview.oldest_approval_days ?? 0,
        error_rate_percent: overview.error_rate ?? 0,
        top_errors: overview.top_errors ?? [],
        avg_processing_time_ms: overview.avg_processing_time_ms ?? 0,
        p95_processing_time_ms: overview.p95_processing_time_ms ?? 0,
        auto_process_rate: overview.auto_process_rate ?? 0,
      };
    } catch (error) {
      console.error('Failed to fetch operations data:', error);
      throw new Error(ERROR_MESSAGES.FETCH_OPERATIONS_FAILED);
    }
  },

  /**
   * Aggregates cashflow-prediction + payment-behavior + smart-dashboard finance KPIs
   */
  async getFinanceData(period: string, customRange?: CustomDateRange): Promise<BackendFinanceData> {
    try {
      const params = buildDateParams(period, customRange);
      const [kpisRes] = await Promise.all([
        apiClient.get('/smart-dashboard/kpis', { params }),
      ]);

      const kpis = kpisRes.data;
      const findKpi = (key: string) => {
        const kpi = Array.isArray(kpis) ? kpis.find((k: { key: string }) => k.key === key) : null;
        return kpi?.value ?? 0;
      };

      // Try to fetch cashflow data (may not be available)
      let cashflowTrend: Array<{ date: string; amount: number }> = [];
      try {
        const cashflowRes = await apiClient.get('/cashflow-prediction/forecast', {
          params: { days: period === 'quarter' ? 90 : 30, ...params },
        });
        cashflowTrend = cashflowRes.data?.forecast ?? [];
      } catch {
        // Cashflow endpoint may not be available
      }

      // Fetch finance tab data for aging buckets and dunning stages
      let agingBuckets: Array<{ bucket: string; count: number; amount: number }> = [];
      let dunningStages: Array<{ stage: number; count: number }> = [];
      try {
        const financeRes = await apiClient.get('/smart-dashboard/tabs/finance', { params });
        agingBuckets = financeRes.data?.aging_buckets ?? [];
        dunningStages = financeRes.data?.dunning_stages ?? [];
      } catch {
        // Finance tab endpoint may not be available
      }

      return {
        open_items_count: findKpi('open_invoices'),
        open_items_amount: findKpi('open_invoices_amount'),
        cashflow_trend: cashflowTrend,
        skonto_realized: findKpi('skonto_realized'),
        skonto_missed: findKpi('skonto_missed'),
        overdue_count: findKpi('overdue'),
        overdue_amount: findKpi('overdue_amount'),
        aging_buckets: agingBuckets,
        dunning_stages: dunningStages,
      };
    } catch (error) {
      console.error('Failed to fetch finance data:', error);
      throw new Error(ERROR_MESSAGES.FETCH_FINANCE_FAILED);
    }
  },

  /**
   * Calls new /analytics/team-stats endpoint
   */
  async getTeamStats(period: string, customRange?: CustomDateRange): Promise<BackendTeamStats> {
    try {
      const params = buildDateParams(period, customRange);
      const response = await apiClient.get<BackendTeamStats>('/analytics/team-stats', {
        params,
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch team stats:', error);
      throw new Error(ERROR_MESSAGES.FETCH_TEAM_FAILED);
    }
  },

  /**
   * Calls /analytics/team-workload for heatmap data
   */
  async getWorkloadData(period: string, customRange?: CustomDateRange): Promise<BackendWorkloadData> {
    try {
      const params = buildDateParams(period, customRange);
      const response = await apiClient.get<BackendWorkloadData>('/analytics/team-workload', {
        params,
      });
      return response.data;
    } catch (error) {
      console.error('Failed to fetch workload data:', error);
      throw new Error(ERROR_MESSAGES.FETCH_WORKLOAD_FAILED);
    }
  },

  /**
   * CSV export helper - generates CSV blob from current tab data
   */
  async exportCSV(tab: AnalyticsTabKey, period: string, customRange?: CustomDateRange): Promise<Blob> {
    try {
      let csvContent = '';

      if (tab === 'team') {
        const data = await analyticsApi.getTeamStats(period, customRange);
        csvContent = 'Benutzer;Dokumente;Ø Freigabezeit (Std.);OCR-Korrekturen;Qualität\n';
        for (const user of data.user_stats) {
          csvContent += `${user.username};${user.documents_processed};${user.avg_approval_time_hours};${user.ocr_corrections};${user.quality_score}\n`;
        }
      } else if (tab === 'finanzen') {
        const data = await analyticsApi.getFinanceData(period, customRange);
        csvContent = 'Metrik;Wert\n';
        csvContent += `Offene Posten;${data.open_items_count}\n`;
        csvContent += `Offener Betrag;${data.open_items_amount}\n`;
        csvContent += `Überfällig;${data.overdue_count}\n`;
        csvContent += `Skonto realisiert;${data.skonto_realized}\n`;
        csvContent += `Skonto verpasst;${data.skonto_missed}\n`;
      } else {
        const data = await analyticsApi.getOperationsData(period, customRange);
        csvContent = 'Metrik;Wert\n';
        csvContent += `Dokumente heute;${data.documents_processed.today}\n`;
        csvContent += `Dokumente Woche;${data.documents_processed.week}\n`;
        csvContent += `Dokumente Monat;${data.documents_processed.month}\n`;
        csvContent += `OCR-Genauigkeit;${data.ocr_accuracy_percent}%\n`;
        csvContent += `Fehlerquote;${data.error_rate_percent}%\n`;
        csvContent += `Automatisierungsrate;${data.auto_process_rate}%\n`;
      }

      return new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    } catch (error) {
      console.error('Failed to generate CSV export:', error);
      throw new Error(ERROR_MESSAGES.EXPORT_FAILED);
    }
  },

  /**
   * PDF export - generates PDF from current tab data using jsPDF
   */
  async exportPDF(tab: AnalyticsTabKey, period: string, customRange?: CustomDateRange): Promise<Blob> {
    try {
      const { jsPDF } = await import('jspdf');
      const doc = new jsPDF();
      const tabTitles: Record<AnalyticsTabKey, string> = {
        betrieb: 'Betrieb',
        finanzen: 'Finanzen',
        team: 'Team',
      };

      // Header
      doc.setFontSize(18);
      doc.text(`Analyse & Berichte - ${tabTitles[tab]}`, 14, 20);
      doc.setFontSize(10);
      const zeitraumLabel = customRange?.startDate
        ? `${customRange.startDate} bis ${customRange.endDate}`
        : period;
      doc.text(`Zeitraum: ${zeitraumLabel} | Erstellt: ${new Date().toLocaleDateString('de-DE')}`, 14, 28);
      doc.setLineWidth(0.5);
      doc.line(14, 31, 196, 31);

      let y = 40;
      doc.setFontSize(11);

      if (tab === 'team') {
        const data = await analyticsApi.getTeamStats(period, customRange);
        doc.text('Benutzer', 14, y);
        doc.text('Dokumente', 80, y);
        doc.text('Freigabezeit', 110, y);
        doc.text('Korrekturen', 145, y);
        doc.text('Qualitaet', 175, y);
        y += 6;
        doc.setLineWidth(0.2);
        doc.line(14, y, 196, y);
        y += 5;
        doc.setFontSize(10);
        for (const user of data.user_stats) {
          if (y > 270) { doc.addPage(); y = 20; }
          doc.text(user.username, 14, y);
          doc.text(String(user.documents_processed), 80, y);
          doc.text(`${user.avg_approval_time_hours}h`, 110, y);
          doc.text(String(user.ocr_corrections), 145, y);
          doc.text(`${user.quality_score}%`, 175, y);
          y += 6;
        }
      } else if (tab === 'finanzen') {
        const data = await analyticsApi.getFinanceData(period, customRange);
        const rows = [
          ['Offene Posten', String(data.open_items_count)],
          ['Offener Betrag', `${data.open_items_amount.toLocaleString('de-DE')} EUR`],
          ['Ueberfaellig', String(data.overdue_count)],
          ['Skonto realisiert', `${data.skonto_realized.toLocaleString('de-DE')} EUR`],
          ['Skonto verpasst', `${data.skonto_missed.toLocaleString('de-DE')} EUR`],
        ];
        for (const [label, value] of rows) {
          doc.text(label, 14, y);
          doc.text(value, 120, y);
          y += 7;
        }
      } else {
        const data = await analyticsApi.getOperationsData(period, customRange);
        const rows = [
          ['Dokumente heute', String(data.documents_processed.today)],
          ['Dokumente Woche', String(data.documents_processed.week)],
          ['Dokumente Monat', String(data.documents_processed.month)],
          ['OCR-Genauigkeit', `${data.ocr_accuracy_percent}%`],
          ['Fehlerquote', `${data.error_rate_percent}%`],
          ['Automatisierungsrate', `${data.auto_process_rate}%`],
        ];
        for (const [label, value] of rows) {
          doc.text(label, 14, y);
          doc.text(value, 120, y);
          y += 7;
        }
      }

      return doc.output('blob');
    } catch (error) {
      console.error('Failed to generate PDF export:', error);
      throw new Error(ERROR_MESSAGES.EXPORT_FAILED);
    }
  },
};
