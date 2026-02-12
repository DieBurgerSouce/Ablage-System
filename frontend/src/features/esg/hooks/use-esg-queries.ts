/**
 * ESG Query Hooks
 *
 * TanStack Query Hooks für das Nachhaltigkeitsberichterstattungs-Modul.
 * Alle Mutations beinhalten Toast-Messages für User-Feedback.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import {
  esgService,
  type ESGScope,
  type RiskLevel,
  type ESGCategory,
  type CertificationStatus,
  type ReportType,
  type ReportStatus,
  type CarbonEmissionCreate,
  type SupplierRatingCreate,
  type CertificationCreate,
  type ReportGenerate,
  type GoalCreate,
  type GoalProgressUpdate,
} from '@/lib/api/services/esg';

// ==================== Stale Time Konfiguration ====================

const STALE_TIMES = {
  dashboard: 2 * 60 * 1000,       // 2 Minuten - Dashboard ändert sich moderat
  emissions: 30 * 1000,           // 30 Sekunden - Emissionen können häufig kommen
  emissionFactors: 60 * 60 * 1000, // 1 Stunde - Faktoren ändern sich selten
  suppliers: 5 * 60 * 1000,       // 5 Minuten
  certifications: 5 * 60 * 1000,  // 5 Minuten - Zertifizierungen ändern sich selten
  reports: 5 * 60 * 1000,         // 5 Minuten
  goals: 2 * 60 * 1000,           // 2 Minuten
  sdg: 60 * 60 * 1000,            // 1 Stunde - SDG-Mapping ändert sich selten
} as const;

// ==================== Query Keys ====================

export const esgQueryKeys = {
  all: ['esg'] as const,

  // Dashboard
  dashboard: () => [...esgQueryKeys.all, 'dashboard'] as const,
  dashboardWithPeriod: (periodStart?: string, periodEnd?: string) =>
    [...esgQueryKeys.dashboard(), { periodStart, periodEnd }] as const,

  // Carbon Footprint
  carbon: () => [...esgQueryKeys.all, 'carbon'] as const,
  emissionFactors: () => [...esgQueryKeys.carbon(), 'factors'] as const,
  emissions: () => [...esgQueryKeys.carbon(), 'emissions'] as const,
  emissionsList: (params?: {
    period_start?: string;
    period_end?: string;
    scope?: ESGScope;
    source_category?: string;
    verified_only?: boolean;
    limit?: number;
    offset?: number;
  }) => [...esgQueryKeys.emissions(), 'list', params] as const,
  emissionsSummary: (periodStart: string, periodEnd: string) =>
    [...esgQueryKeys.carbon(), 'summary', { periodStart, periodEnd }] as const,
  carbonTrend: (months: number) =>
    [...esgQueryKeys.carbon(), 'trend', months] as const,

  // Supplier Ratings
  suppliers: () => [...esgQueryKeys.all, 'suppliers'] as const,
  ratingCriteria: () => [...esgQueryKeys.suppliers(), 'criteria'] as const,
  ratings: () => [...esgQueryKeys.suppliers(), 'ratings'] as const,
  ratingsList: (params?: {
    entity_id?: string;
    risk_level?: RiskLevel;
    min_score?: number;
    max_score?: number;
    limit?: number;
    offset?: number;
  }) => [...esgQueryKeys.ratings(), 'list', params] as const,
  riskSummary: () => [...esgQueryKeys.suppliers(), 'risk-summary'] as const,
  latestRating: (entityId: string) =>
    [...esgQueryKeys.ratings(), 'latest', entityId] as const,

  // Certifications
  certifications: () => [...esgQueryKeys.all, 'certifications'] as const,
  certificationTypes: () => [...esgQueryKeys.certifications(), 'types'] as const,
  certificationsList: (params?: {
    category?: ESGCategory;
    status?: CertificationStatus;
    include_expired?: boolean;
    limit?: number;
    offset?: number;
  }) => [...esgQueryKeys.certifications(), 'list', params] as const,
  certificationSummary: () =>
    [...esgQueryKeys.certifications(), 'summary'] as const,
  expiring: (days: number) =>
    [...esgQueryKeys.certifications(), 'expiring', days] as const,
  upcomingAudits: (days: number) =>
    [...esgQueryKeys.certifications(), 'upcoming-audits', days] as const,
  certificationDetail: (id: string) =>
    [...esgQueryKeys.certifications(), 'detail', id] as const,

  // Reports
  reports: () => [...esgQueryKeys.all, 'reports'] as const,
  reportTemplates: () => [...esgQueryKeys.reports(), 'templates'] as const,
  reportsList: (params?: {
    report_type?: ReportType;
    status?: ReportStatus;
    limit?: number;
    offset?: number;
  }) => [...esgQueryKeys.reports(), 'list', params] as const,
  reportDetail: (id: string) =>
    [...esgQueryKeys.reports(), 'detail', id] as const,

  // Goals
  goals: () => [...esgQueryKeys.all, 'goals'] as const,
  goalsList: (params?: { category?: ESGCategory; active_only?: boolean }) =>
    [...esgQueryKeys.goals(), 'list', params] as const,

  // SDG Mapping
  sdg: () => [...esgQueryKeys.all, 'sdg'] as const,
  sdgMapping: () => [...esgQueryKeys.sdg(), 'mapping'] as const,
};

// Legacy key export for backward compatibility
export const esgKeys = esgQueryKeys;

// ==================== Dashboard Hooks ====================

export function useESGDashboard(periodStart?: string, periodEnd?: string) {
  return useQuery({
    queryKey: esgQueryKeys.dashboardWithPeriod(periodStart, periodEnd),
    queryFn: () => esgService.getDashboard({ period_start: periodStart, period_end: periodEnd }),
    staleTime: STALE_TIMES.dashboard,
  });
}

// ==================== Carbon Footprint Hooks ====================

export function useEmissionFactors() {
  return useQuery({
    queryKey: esgQueryKeys.emissionFactors(),
    queryFn: () => esgService.getEmissionFactors(),
    staleTime: STALE_TIMES.emissionFactors,
  });
}

export function useEmissions(params?: {
  period_start?: string;
  period_end?: string;
  scope?: ESGScope;
  source_category?: string;
  verified_only?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: esgQueryKeys.emissionsList(params),
    queryFn: () => esgService.getEmissions(params),
    staleTime: STALE_TIMES.emissions,
  });
}

export function useEmissionsSummary(periodStart: string, periodEnd: string, enabled = true) {
  return useQuery({
    queryKey: esgQueryKeys.emissionsSummary(periodStart, periodEnd),
    queryFn: () => esgService.getEmissionsSummary({ period_start: periodStart, period_end: periodEnd }),
    staleTime: STALE_TIMES.emissions,
    enabled: enabled && !!periodStart && !!periodEnd,
  });
}

export function useCarbonTrend(months = 12) {
  return useQuery({
    queryKey: esgQueryKeys.carbonTrend(months),
    queryFn: () => esgService.getCarbonTrend(months),
    staleTime: STALE_TIMES.dashboard,
  });
}

export function useCalculateEmissions() {
  return useMutation({
    mutationFn: (params: {
      source_category: string;
      consumption_value: number;
      custom_factor?: number;
    }) => esgService.calculateEmissions(params),
  });
}

export function useRecordEmissions(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CarbonEmissionCreate) => esgService.recordEmissions(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.carbon() });
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.dashboard() });
      toast({
        title: ESG_TOAST_MESSAGES.emission.success,
        description: `${result.co2_equivalent_kg.toFixed(2)} kg CO2e erfasst`,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.emission.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Supplier Rating Hooks ====================

export function useRatingCriteria() {
  return useQuery({
    queryKey: esgQueryKeys.ratingCriteria(),
    queryFn: () => esgService.getRatingCriteria(),
    staleTime: STALE_TIMES.emissionFactors,
  });
}

export function useSupplierRatings(params?: {
  entity_id?: string;
  risk_level?: RiskLevel;
  min_score?: number;
  max_score?: number;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: esgQueryKeys.ratingsList(params),
    queryFn: () => esgService.getSupplierRatings(params),
    staleTime: STALE_TIMES.suppliers,
  });
}

export function useSupplierRiskSummary() {
  return useQuery({
    queryKey: esgQueryKeys.riskSummary(),
    queryFn: () => esgService.getSupplierRiskSummary(),
    staleTime: STALE_TIMES.suppliers,
  });
}

export function useLatestSupplierRating(entityId: string, enabled = true) {
  return useQuery({
    queryKey: esgQueryKeys.latestRating(entityId),
    queryFn: () => esgService.getLatestSupplierRating(entityId),
    staleTime: STALE_TIMES.suppliers,
    enabled: enabled && !!entityId,
  });
}

export function useCreateSupplierRating(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: SupplierRatingCreate) => esgService.createSupplierRating(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.suppliers() });
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.dashboard() });
      toast({
        title: ESG_TOAST_MESSAGES.supplierRating.success,
        description: `Gesamtbewertung: ${result.overall_score}/100 (${getRiskLevelLabel(result.risk_level)})`,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.supplierRating.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Certification Hooks ====================

export function useCertificationTypes() {
  return useQuery({
    queryKey: esgQueryKeys.certificationTypes(),
    queryFn: () => esgService.getCertificationTypes(),
    staleTime: STALE_TIMES.emissionFactors,
  });
}

export function useCertifications(params?: {
  category?: ESGCategory;
  status?: CertificationStatus;
  include_expired?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: esgQueryKeys.certificationsList(params),
    queryFn: () => esgService.getCertifications(params),
    staleTime: STALE_TIMES.certifications,
  });
}

export function useCertificationSummary() {
  return useQuery({
    queryKey: esgQueryKeys.certificationSummary(),
    queryFn: () => esgService.getCertificationSummary(),
    staleTime: STALE_TIMES.certifications,
  });
}

export function useExpiringCertifications(days = 90) {
  return useQuery({
    queryKey: esgQueryKeys.expiring(days),
    queryFn: () => esgService.getExpiringCertifications(days),
    staleTime: STALE_TIMES.certifications,
  });
}

export function useUpcomingAudits(days = 60) {
  return useQuery({
    queryKey: esgQueryKeys.upcomingAudits(days),
    queryFn: () => esgService.getUpcomingAudits(days),
    staleTime: STALE_TIMES.certifications,
  });
}

export function useCertificationDetail(certificationId: string, enabled = true) {
  return useQuery({
    queryKey: esgQueryKeys.certificationDetail(certificationId),
    queryFn: () => esgService.getCertificationDetail(certificationId),
    staleTime: STALE_TIMES.certifications,
    enabled: enabled && !!certificationId,
  });
}

export function useAddCertification(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CertificationCreate) => esgService.addCertification(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.certifications() });
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.dashboard() });
      toast({
        title: ESG_TOAST_MESSAGES.certification.success,
        description: 'Zertifizierung wurde erfolgreich hinzugefügt',
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.certification.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Report Hooks ====================

export function useReportTemplates() {
  return useQuery({
    queryKey: esgQueryKeys.reportTemplates(),
    queryFn: () => esgService.getReportTemplates(),
    staleTime: STALE_TIMES.emissionFactors,
  });
}

export function useReports(params?: {
  report_type?: ReportType;
  status?: ReportStatus;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: esgQueryKeys.reportsList(params),
    queryFn: () => esgService.getReports(params),
    staleTime: STALE_TIMES.reports,
  });
}

// Alias for backward compatibility
export const useESGReports = useReports;

export function useReportDetail(reportId: string, enabled = true) {
  return useQuery({
    queryKey: esgQueryKeys.reportDetail(reportId),
    queryFn: () => esgService.getReportDetail(reportId),
    staleTime: STALE_TIMES.reports,
    enabled: enabled && !!reportId,
  });
}

export function useGenerateReport(options?: {
  onSuccess?: (reportId: string, title: string) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: ReportGenerate) => esgService.generateReport(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.reports() });
      toast({
        title: ESG_TOAST_MESSAGES.report.success,
        description: `Bericht "${result.title}" wurde erfolgreich erstellt`,
        variant: 'success',
      });
      options?.onSuccess?.(result.report_id, result.title);
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.report.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Goal Hooks ====================

export function useGoals(params?: { category?: ESGCategory; active_only?: boolean }) {
  return useQuery({
    queryKey: esgQueryKeys.goalsList(params),
    queryFn: () => esgService.getGoals(params),
    staleTime: STALE_TIMES.goals,
  });
}

// Alias for backward compatibility
export const useESGGoals = useGoals;

export function useCreateGoal(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: GoalCreate) => esgService.createGoal(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.goals() });
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.dashboard() });
      toast({
        title: ESG_TOAST_MESSAGES.goal.success,
        description: 'Nachhaltigkeitsziel wurde erfolgreich erstellt',
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.goal.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

export function useUpdateGoalProgress(options?: {
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ goalId, data }: { goalId: string; data: GoalProgressUpdate }) =>
      esgService.updateGoalProgress(goalId, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.goals() });
      queryClient.invalidateQueries({ queryKey: esgQueryKeys.dashboard() });
      const statusText = result.on_track ? 'auf Kurs' : 'nicht auf Kurs';
      toast({
        title: ESG_TOAST_MESSAGES.goalProgress.success,
        description: `Fortschritt: ${result.progress_percentage.toFixed(1)}% (${statusText})`,
        variant: 'success',
      });
      options?.onSuccess?.();
    },
    onError: (error: Error) => {
      toast({
        title: ESG_TOAST_MESSAGES.goalProgress.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== SDG Mapping Hooks ====================

export function useSDGMapping() {
  return useQuery({
    queryKey: esgQueryKeys.sdgMapping(),
    queryFn: () => esgService.getSDGMapping(),
    staleTime: STALE_TIMES.sdg,
  });
}

// ==================== Toast Messages ====================

/**
 * Standard-Toast-Nachrichten für ESG-Operationen.
 * Verwendung in Komponenten für konsistentes deutsches Feedback.
 */
export const ESG_TOAST_MESSAGES = {
  emission: {
    success: 'Emissionen erfolgreich erfasst',
    error: 'Fehler beim Erfassen der Emissionen',
  },
  supplierRating: {
    success: 'Lieferantenbewertung erstellt',
    error: 'Fehler beim Erstellen der Bewertung',
  },
  certification: {
    success: 'Zertifizierung hinzugefügt',
    error: 'Fehler beim Hinzufügen der Zertifizierung',
  },
  report: {
    success: 'Bericht erstellt',
    error: 'Fehler beim Erstellen des Berichts',
  },
  goal: {
    success: 'Ziel erstellt',
    error: 'Fehler beim Erstellen des Ziels',
  },
  goalProgress: {
    success: 'Fortschritt aktualisiert',
    error: 'Fehler beim Aktualisieren des Fortschritts',
  },
} as const;

// ==================== Helper Functions ====================

/**
 * Gibt deutsches Label für Risiko-Level zurück
 */
function getRiskLevelLabel(riskLevel: string): string {
  const labels: Record<string, string> = {
    low: 'Niedriges Risiko',
    medium: 'Mittleres Risiko',
    high: 'Hohes Risiko',
    critical: 'Kritisches Risiko',
  };
  return labels[riskLevel] || riskLevel;
}

/**
 * Gibt deutsches Label für ESG-Kategorie zurück
 */
export function getCategoryLabel(category: ESGCategory): string {
  const labels: Record<ESGCategory, string> = {
    environmental: 'Umwelt',
    social: 'Soziales',
    governance: 'Unternehmensführung',
  };
  return labels[category];
}

/**
 * Gibt deutsches Label für Scope zurück
 */
export function getScopeLabel(scope: string): string {
  const labels: Record<string, string> = {
    scope_1: 'Scope 1 (Direkt)',
    scope_2: 'Scope 2 (Energie)',
    scope_3: 'Scope 3 (Indirekt)',
  };
  return labels[scope] || scope;
}

/**
 * Gibt deutsches Label für Zertifizierungsstatus zurück
 */
export function getCertificationStatusLabel(status: CertificationStatus): string {
  const labels: Record<CertificationStatus, string> = {
    active: 'Aktiv',
    expired: 'Abgelaufen',
    pending: 'Ausstehend',
    revoked: 'Widerrufen',
  };
  return labels[status];
}

/**
 * Gibt deutsches Label für Berichtsstatus zurück
 */
export function getReportStatusLabel(status: ReportStatus): string {
  const labels: Record<ReportStatus, string> = {
    draft: 'Entwurf',
    in_review: 'In Prüfung',
    approved: 'Genehmigt',
    published: 'Veröffentlicht',
    archived: 'Archiviert',
  };
  return labels[status];
}
