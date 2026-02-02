/**
 * OCR Feedback API Client
 *
 * API fuer das OCR-Korrektur-System mit Gamification.
 * Leaderboard, Punkte, Achievements und Korrektur-Queue.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  username: string;
  full_name: string | null;
  corrections_count: number;
  total_points: number;
  accuracy_rate: number;
  current_streak: number;
  longest_streak: number;
  achievements: string[];
  is_current_user: boolean;
}

export interface LeaderboardResponse {
  period: 'weekly' | 'monthly' | 'all_time';
  entries: LeaderboardEntry[];
}

export interface UserStats {
  user_id: string;
  total_corrections: number;
  total_points: number;
  current_streak: number;
  longest_streak: number;
  weekly_corrections: number;
  weekly_points: number;
  monthly_corrections: number;
  monthly_points: number;
  weekly_rank: number | null;
  monthly_rank: number | null;
  accuracy_rate: number;
  achievements: string[];
  recent_corrections: RecentCorrection[];
  points_breakdown: Record<string, number>;
}

export interface RecentCorrection {
  id: string;
  field_name: string;
  points: number;
  created_at: string;
}

export interface QueueItem {
  id: string;
  document_id: string;
  document_filename: string;
  field_name: string;
  ocr_value: string;
  confidence: number;
  priority: 'critical' | 'high' | 'medium' | 'low';
  ocr_backend: string;
  document_type: string | null;
  entity_name: string | null;
  page_number: number | null;
  context_text: string | null;
  suggested_value: string | null;
  created_at: string;
}

export interface QueueResponse {
  total: number;
  limit: number;
  offset: number;
  items: QueueItem[];
}

export interface CorrectionRequest {
  document_id: string;
  field_name: string;
  original_value: string;
  corrected_value: string;
  confidence_before: number;
  correction_type?: 'text' | 'amount' | 'date' | 'entity' | 'iban' | 'vat_id' | 'reference';
  ocr_backend?: string;
  page_number?: number;
  bounding_box?: { x: number; y: number; width: number; height: number };
  context_text?: string;
}

export interface CorrectionResult {
  correction_id: string;
  document_id: string;
  field_name: string;
  applied: boolean;
  points_awarded: number;
  bonus_points: number;
  total_points: number;
  new_user_total: number;
  new_streak: number;
  achievements_unlocked: string[];
  feedback_message: string;
}

export interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  unlocked: boolean;
}

export interface AchievementsResponse {
  total_achievements: number;
  unlocked_count: number;
  achievements: Achievement[];
}

export type LeaderboardPeriod = 'weekly' | 'monthly' | 'all_time';
export type QueuePriority = 'critical' | 'high' | 'medium' | 'low';

// ==================== API Functions ====================

/**
 * Leaderboard abrufen
 */
export async function getLeaderboard(
  period: LeaderboardPeriod = 'weekly',
  limit: number = 10
): Promise<LeaderboardResponse> {
  const response = await apiClient.get<LeaderboardResponse>('/ocr-feedback/leaderboard', {
    params: { period, limit },
  });
  return response.data;
}

/**
 * Eigene Statistiken abrufen
 */
export async function getUserStats(): Promise<UserStats> {
  const response = await apiClient.get<UserStats>('/ocr-feedback/stats');
  return response.data;
}

/**
 * Statistiken eines bestimmten Benutzers abrufen (Admin)
 */
export async function getUserStatsById(userId: string): Promise<UserStats> {
  const response = await apiClient.get<UserStats>(`/ocr-feedback/stats/${userId}`);
  return response.data;
}

/**
 * Korrektur-Queue abrufen
 */
export async function getCorrectionQueue(params?: {
  priority?: QueuePriority;
  document_type?: string;
  limit?: number;
  offset?: number;
}): Promise<QueueResponse> {
  const response = await apiClient.get<QueueResponse>('/ocr-feedback/queue', { params });
  return response.data;
}

/**
 * Queue-Item reservieren
 */
export async function claimQueueItem(itemId: string): Promise<{
  item_id: string;
  claimed: boolean;
  claimed_by: string;
  message: string;
}> {
  const response = await apiClient.post(`/ocr-feedback/queue/${itemId}/claim`);
  return response.data;
}

/**
 * Korrektur einreichen
 */
export async function submitCorrection(request: CorrectionRequest): Promise<CorrectionResult> {
  const response = await apiClient.post<CorrectionResult>('/ocr-feedback/correction', request);
  return response.data;
}

/**
 * Batch-Korrekturen einreichen
 */
export async function submitBatchCorrections(corrections: CorrectionRequest[]): Promise<{
  batch_id: string;
  total_corrections: number;
  applied_count: number;
  rejected_count: number;
  total_points_awarded: number;
  processing_time_ms: number;
  errors: Array<{ document_id: string; field_name: string; error: string }>;
}> {
  const response = await apiClient.post('/ocr-feedback/batch', { corrections });
  return response.data;
}

/**
 * Achievements abrufen
 */
export async function getAchievements(): Promise<AchievementsResponse> {
  const response = await apiClient.get<AchievementsResponse>('/ocr-feedback/achievements');
  return response.data;
}
