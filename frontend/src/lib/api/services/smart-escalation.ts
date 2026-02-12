/**
 * Smart Escalation API Service
 *
 * Kommuniziert mit den /api/v1/smart-escalation Endpoints
 * für KI-gestützte intelligente Aufgabenzuweisung
 *
 * Features:
 * - Zuweisungsempfehlungen basierend auf KI-Faktoren
 * - Team-Auslastungsübersicht
 * - User-Score Debugging/Analyse
 * - Verfügbare Faktoren und Gewichtungen
 *
 * Phase 2.3 der Feature-Roadmap (Januar 2026)
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Classes ====================

export class SmartEscalationApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'SmartEscalationApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Enums ====================

export type AssignmentFactor = 'expertise' | 'workload' | 'availability' | 'relationship';

// ==================== Frontend Types ====================

export interface FactorWeights {
  expertise: number;
  workload: number;
  availability: number;
  relationship: number;
}

export interface CandidateScore {
  userId: string;
  userEmail: string;
  userName: string;

  expertiseScore: number;
  workloadScore: number;
  availabilityScore: number;
  relationshipScore: number;
  totalScore: number;

  expertiseDetails: Record<string, unknown>;
  workloadDetails: Record<string, unknown>;
  availabilityDetails: Record<string, unknown>;
  relationshipDetails: Record<string, unknown>;

  isAvailable: boolean;
  unavailabilityReason?: string;
}

export interface AssignmentRecommendation {
  recommendedUserId: string;
  recommendedUserName: string;
  confidence: number;

  candidates: CandidateScore[];

  factorsUsed: AssignmentFactor[];
  weightsUsed: FactorWeights;

  explanation: string;
  explanationDetails: Record<string, unknown>;
}

export interface TeamMemberWorkload {
  userId: string;
  userName: string;
  openItems: number;
  workloadScore: number;
  isAvailable: boolean;
  availabilityScore: number;
}

export interface TeamWorkload {
  teamMembers: TeamMemberWorkload[];
  totalOpenItems: number;
  availableMembers: number;
  totalMembers: number;
  avgItemsPerMember: number;
}

export interface FactorInfo {
  name: string;
  description: string;
  defaultWeight: number;
}

export interface FactorsResponse {
  factors: FactorInfo[];
  defaultWeights: FactorWeights;
  scoreRange: { min: number; max: number };
  thresholds: {
    minExpertiseTasks: number;
    maxWorkloadItems: number;
    expertisePeriodDays: number;
    relationshipPeriodDays: number;
  };
}

// ==================== Request Types ====================

export interface AssignmentRequest {
  documentId?: string;
  documentType?: string;
  entityId?: string;
  taskType?: string;
  excludeUserIds?: string[];
  weights?: Partial<FactorWeights>;
  maxCandidates?: number;
}

export interface UserScoresFilter {
  documentType?: string;
  entityId?: string;
}

// ==================== Backend Types ====================

interface CandidateScoreBackend {
  user_id: string;
  user_email: string;
  user_name: string;

  expertise_score: number;
  workload_score: number;
  availability_score: number;
  relationship_score: number;
  total_score: number;

  expertise_details: Record<string, unknown>;
  workload_details: Record<string, unknown>;
  availability_details: Record<string, unknown>;
  relationship_details: Record<string, unknown>;

  is_available: boolean;
  unavailability_reason: string | null;
}

interface AssignmentRecommendationBackend {
  recommended_user_id: string;
  recommended_user_name: string;
  confidence: number;

  candidates: CandidateScoreBackend[];

  factors_used: string[];
  weights_used: {
    expertise: number;
    workload: number;
    availability: number;
    relationship: number;
  };

  explanation: string;
  explanation_details: Record<string, unknown>;
}

interface TeamMemberWorkloadBackend {
  user_id: string;
  user_name: string;
  open_items: number;
  workload_score: number;
  is_available: boolean;
  availability_score: number;
}

interface TeamWorkloadBackend {
  team_members: TeamMemberWorkloadBackend[];
  total_open_items: number;
  available_members: number;
  total_members: number;
  avg_items_per_member: number;
}

interface FactorInfoBackend {
  name: string;
  description: string;
  default_weight: number;
}

interface FactorsBackend {
  factors: FactorInfoBackend[];
  default_weights: {
    expertise: number;
    workload: number;
    availability: number;
    relationship: number;
  };
  score_range: { min: number; max: number };
  thresholds: {
    min_expertise_tasks: number;
    max_workload_items: number;
    expertise_period_days: number;
    relationship_period_days: number;
  };
}

// ==================== Transformers ====================

function transformCandidateScore(c: CandidateScoreBackend): CandidateScore {
  return {
    userId: c.user_id,
    userEmail: c.user_email,
    userName: c.user_name,
    expertiseScore: c.expertise_score,
    workloadScore: c.workload_score,
    availabilityScore: c.availability_score,
    relationshipScore: c.relationship_score,
    totalScore: c.total_score,
    expertiseDetails: c.expertise_details,
    workloadDetails: c.workload_details,
    availabilityDetails: c.availability_details,
    relationshipDetails: c.relationship_details,
    isAvailable: c.is_available,
    unavailabilityReason: c.unavailability_reason ?? undefined,
  };
}

function transformRecommendation(r: AssignmentRecommendationBackend): AssignmentRecommendation {
  return {
    recommendedUserId: r.recommended_user_id,
    recommendedUserName: r.recommended_user_name,
    confidence: r.confidence,
    candidates: r.candidates.map(transformCandidateScore),
    factorsUsed: r.factors_used as AssignmentFactor[],
    weightsUsed: r.weights_used,
    explanation: r.explanation,
    explanationDetails: r.explanation_details,
  };
}

function transformTeamMember(m: TeamMemberWorkloadBackend): TeamMemberWorkload {
  return {
    userId: m.user_id,
    userName: m.user_name,
    openItems: m.open_items,
    workloadScore: m.workload_score,
    isAvailable: m.is_available,
    availabilityScore: m.availability_score,
  };
}

function transformTeamWorkload(t: TeamWorkloadBackend): TeamWorkload {
  return {
    teamMembers: t.team_members.map(transformTeamMember),
    totalOpenItems: t.total_open_items,
    availableMembers: t.available_members,
    totalMembers: t.total_members,
    avgItemsPerMember: t.avg_items_per_member,
  };
}

function transformFactors(f: FactorsBackend): FactorsResponse {
  return {
    factors: f.factors.map((factor) => ({
      name: factor.name,
      description: factor.description,
      defaultWeight: factor.default_weight,
    })),
    defaultWeights: f.default_weights,
    scoreRange: f.score_range,
    thresholds: {
      minExpertiseTasks: f.thresholds.min_expertise_tasks,
      maxWorkloadItems: f.thresholds.max_workload_items,
      expertisePeriodDays: f.thresholds.expertise_period_days,
      relationshipPeriodDays: f.thresholds.relationship_period_days,
    },
  };
}

// ==================== Request Transformers ====================

function transformAssignmentRequest(r: AssignmentRequest): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  if (r.documentId) result.document_id = r.documentId;
  if (r.documentType) result.document_type = r.documentType;
  if (r.entityId) result.entity_id = r.entityId;
  if (r.taskType) result.task_type = r.taskType;
  if (r.excludeUserIds) result.exclude_user_ids = r.excludeUserIds;
  if (r.maxCandidates) result.max_candidates = r.maxCandidates;

  if (r.weights) {
    result.weights = {
      expertise: r.weights.expertise ?? 0.35,
      workload: r.weights.workload ?? 0.25,
      availability: r.weights.availability ?? 0.25,
      relationship: r.weights.relationship ?? 0.15,
    };
  }

  return result;
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new SmartEscalationApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new SmartEscalationApiError(`${context}: ${message}`, 400, error);
    }

    throw new SmartEscalationApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new SmartEscalationApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Service ====================

export const smartEscalationService = {
  /**
   * Holt Zuweisungsempfehlung (POST)
   */
  getRecommendation: async (request: AssignmentRequest): Promise<AssignmentRecommendation> => {
    try {
      const response = await apiClient.post<AssignmentRecommendationBackend>(
        '/smart-escalation/recommend',
        transformAssignmentRequest(request)
      );
      return transformRecommendation(response.data);
    } catch (error) {
      handleApiError(error, 'Zuweisungsempfehlung laden');
    }
  },

  /**
   * Holt Zuweisungsempfehlung (GET mit Query-Params)
   */
  getRecommendationQuery: async (params: {
    documentId?: string;
    documentType?: string;
    entityId?: string;
    taskType?: string;
    maxCandidates?: number;
  }): Promise<AssignmentRecommendation> => {
    try {
      const queryParams = new URLSearchParams();
      if (params.documentId) queryParams.append('document_id', params.documentId);
      if (params.documentType) queryParams.append('document_type', params.documentType);
      if (params.entityId) queryParams.append('entity_id', params.entityId);
      if (params.taskType) queryParams.append('task_type', params.taskType);
      if (params.maxCandidates) queryParams.append('max_candidates', String(params.maxCandidates));

      const url = `/smart-escalation/recommend${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
      const response = await apiClient.get<AssignmentRecommendationBackend>(url);
      return transformRecommendation(response.data);
    } catch (error) {
      handleApiError(error, 'Zuweisungsempfehlung laden');
    }
  },

  /**
   * Holt Team-Auslastungsübersicht
   */
  getTeamWorkload: async (): Promise<TeamWorkload> => {
    try {
      const response = await apiClient.get<TeamWorkloadBackend>('/smart-escalation/team-workload');
      return transformTeamWorkload(response.data);
    } catch (error) {
      handleApiError(error, 'Team-Auslastung laden');
    }
  },

  /**
   * Holt User-Scores für Debugging/Analyse
   */
  getUserScores: async (userId: string, filter?: UserScoresFilter): Promise<CandidateScore> => {
    try {
      const queryParams = new URLSearchParams();
      if (filter?.documentType) queryParams.append('document_type', filter.documentType);
      if (filter?.entityId) queryParams.append('entity_id', filter.entityId);

      const url = `/smart-escalation/user-scores/${userId}${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
      const response = await apiClient.get<CandidateScoreBackend>(url);
      return transformCandidateScore(response.data);
    } catch (error) {
      handleApiError(error, 'User-Scores laden');
    }
  },

  /**
   * Holt verfügbare Faktoren und Konfiguration
   */
  getFactors: async (): Promise<FactorsResponse> => {
    try {
      const response = await apiClient.get<FactorsBackend>('/smart-escalation/factors');
      return transformFactors(response.data);
    } catch (error) {
      handleApiError(error, 'Faktoren laden');
    }
  },
};
