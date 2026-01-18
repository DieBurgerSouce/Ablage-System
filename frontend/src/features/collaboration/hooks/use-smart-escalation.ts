/**
 * Smart Escalation Hooks
 *
 * TanStack Query Hooks fuer KI-gestuetzte intelligente Aufgabenzuweisung
 *
 * Features:
 * - Zuweisungsempfehlungen abrufen
 * - Team-Auslastung anzeigen
 * - User-Scores debuggen
 * - Faktoren und Gewichtungen konfigurieren
 *
 * Phase 2.3 der Feature-Roadmap (Januar 2026)
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  smartEscalationService,
  type AssignmentRequest,
  type UserScoresFilter,
  type AssignmentRecommendation,
  type TeamWorkload,
  type CandidateScore,
  type FactorsResponse,
} from '@/lib/api/services/smart-escalation';

// ==================== Query Keys ====================

export const smartEscalationQueryKeys = {
  all: ['smart-escalation'] as const,

  // Recommendations
  recommendations: () => [...smartEscalationQueryKeys.all, 'recommendations'] as const,
  recommendation: (request: AssignmentRequest) =>
    [...smartEscalationQueryKeys.recommendations(), request] as const,

  // Team Workload
  teamWorkload: () => [...smartEscalationQueryKeys.all, 'team-workload'] as const,

  // User Scores
  userScores: () => [...smartEscalationQueryKeys.all, 'user-scores'] as const,
  userScore: (userId: string, filter?: UserScoresFilter) =>
    [...smartEscalationQueryKeys.userScores(), userId, filter] as const,

  // Factors
  factors: () => [...smartEscalationQueryKeys.all, 'factors'] as const,
};

// ==================== Stale Times ====================

const STALE_TIMES = {
  recommendation: 1000 * 60, // 1 Minute
  teamWorkload: 1000 * 30, // 30 Sekunden (haeufiger aktualisieren)
  userScores: 1000 * 60 * 2, // 2 Minuten
  factors: 1000 * 60 * 30, // 30 Minuten (selten aendernd)
};

// ==================== Query Hooks ====================

/**
 * Holt Zuweisungsempfehlung fuer eine Aufgabe
 *
 * @param request - Parameter fuer die Empfehlung
 * @param enabled - Ob die Query aktiv ist
 */
export function useAssignmentRecommendation(
  request: AssignmentRequest,
  enabled = true
) {
  return useQuery({
    queryKey: smartEscalationQueryKeys.recommendation(request),
    queryFn: () => smartEscalationService.getRecommendation(request),
    staleTime: STALE_TIMES.recommendation,
    enabled,
  });
}

/**
 * Holt Zuweisungsempfehlung via GET (fuer einfache Faelle)
 *
 * @param params - Query-Parameter
 * @param enabled - Ob die Query aktiv ist
 */
export function useAssignmentRecommendationQuery(
  params: {
    documentId?: string;
    documentType?: string;
    entityId?: string;
    taskType?: string;
    maxCandidates?: number;
  },
  enabled = true
) {
  return useQuery({
    queryKey: smartEscalationQueryKeys.recommendation(params),
    queryFn: () => smartEscalationService.getRecommendationQuery(params),
    staleTime: STALE_TIMES.recommendation,
    enabled,
  });
}

/**
 * Holt Team-Auslastungsuebersicht
 *
 * Zeigt Auslastung aller Team-Mitglieder mit:
 * - Anzahl offener Items
 * - Workload-Score
 * - Verfuegbarkeits-Status
 */
export function useTeamWorkload() {
  return useQuery({
    queryKey: smartEscalationQueryKeys.teamWorkload(),
    queryFn: () => smartEscalationService.getTeamWorkload(),
    staleTime: STALE_TIMES.teamWorkload,
    refetchInterval: 1000 * 60, // Alle 60 Sekunden refetchen
  });
}

/**
 * Holt detaillierte Scores eines Users
 *
 * Nuetzlich fuer Debugging und Analyse der Score-Berechnung
 *
 * @param userId - User-ID
 * @param filter - Optionale Filter (documentType, entityId)
 * @param enabled - Ob die Query aktiv ist
 */
export function useUserScores(
  userId: string,
  filter?: UserScoresFilter,
  enabled = true
) {
  return useQuery({
    queryKey: smartEscalationQueryKeys.userScore(userId, filter),
    queryFn: () => smartEscalationService.getUserScores(userId, filter),
    staleTime: STALE_TIMES.userScores,
    enabled: !!userId && enabled,
  });
}

/**
 * Holt verfuegbare Faktoren und Konfiguration
 *
 * Enthaelt:
 * - Liste der Faktoren mit Beschreibungen
 * - Standard-Gewichtungen
 * - Score-Bereich
 * - Schwellenwerte
 */
export function useEscalationFactors() {
  return useQuery({
    queryKey: smartEscalationQueryKeys.factors(),
    queryFn: () => smartEscalationService.getFactors(),
    staleTime: STALE_TIMES.factors,
  });
}

// ==================== Utility Hooks ====================

/**
 * Invalidiert alle Smart Escalation Queries
 */
export function useInvalidateSmartEscalationQueries() {
  const queryClient = useQueryClient();

  return {
    invalidateAll: () => {
      queryClient.invalidateQueries({
        queryKey: smartEscalationQueryKeys.all,
      });
    },
    invalidateRecommendations: () => {
      queryClient.invalidateQueries({
        queryKey: smartEscalationQueryKeys.recommendations(),
      });
    },
    invalidateTeamWorkload: () => {
      queryClient.invalidateQueries({
        queryKey: smartEscalationQueryKeys.teamWorkload(),
      });
    },
    invalidateUserScores: () => {
      queryClient.invalidateQueries({
        queryKey: smartEscalationQueryKeys.userScores(),
      });
    },
  };
}

/**
 * Prefetch Team-Workload fuer schnellere Darstellung
 */
export function usePrefetchTeamWorkload() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.prefetchQuery({
      queryKey: smartEscalationQueryKeys.teamWorkload(),
      queryFn: () => smartEscalationService.getTeamWorkload(),
      staleTime: STALE_TIMES.teamWorkload,
    });
  };
}

/**
 * Prefetch Faktoren fuer schnellere Darstellung
 */
export function usePrefetchFactors() {
  const queryClient = useQueryClient();

  return () => {
    queryClient.prefetchQuery({
      queryKey: smartEscalationQueryKeys.factors(),
      queryFn: () => smartEscalationService.getFactors(),
      staleTime: STALE_TIMES.factors,
    });
  };
}

// ==================== Re-exports ====================

export type {
  AssignmentRequest,
  UserScoresFilter,
  AssignmentRecommendation,
  TeamWorkload,
  CandidateScore,
  FactorsResponse,
  FactorWeights,
  TeamMemberWorkload,
  FactorInfo,
  AssignmentFactor,
} from '@/lib/api/services/smart-escalation';
