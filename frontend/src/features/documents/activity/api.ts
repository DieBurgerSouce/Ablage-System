/**
 * Activity Timeline API
 *
 * API-Funktionen für das Activity Timeline Feature.
 */

import { apiClient } from '@/lib/api';
import type {
  Activity,
  TimelineResponse,
  TimelineFilter,
  ActivityStatistics,
  ActivitySource,
} from './types';

// =============================================================================
// API Response Types (snake_case from backend)
// =============================================================================

interface ApiActivity {
  id: string;
  source: ActivitySource;
  activity_type: string;
  title: string;
  description?: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_avatar?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  target_name?: string | null;
  related_type?: string | null;
  related_id?: string | null;
  related_name?: string | null;
  company_id?: string | null;
  team_id?: string | null;
  chain_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  icon?: string | null;
  color?: string | null;
  is_important: boolean;
}

interface ApiTimelineResponse {
  items: ApiActivity[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

interface ApiStatistics {
  total_activities: number;
  activities_by_type: Record<string, number>;
  activities_by_day: Array<{ date: string | null; count: number }>;
  top_users: Array<{
    user_id: string;
    user_name: string;
    activity_count: number;
  }>;
  date_range: {
    from: string;
    until: string;
  };
}

// =============================================================================
// Converters
// =============================================================================

function convertActivity(api: ApiActivity): Activity {
  return {
    id: api.id,
    source: api.source,
    activityType: api.activity_type,
    title: api.title,
    description: api.description,
    actorId: api.actor_id,
    actorName: api.actor_name,
    actorAvatar: api.actor_avatar,
    targetType: api.target_type,
    targetId: api.target_id,
    targetName: api.target_name,
    relatedType: api.related_type,
    relatedId: api.related_id,
    relatedName: api.related_name,
    companyId: api.company_id,
    teamId: api.team_id,
    chainId: api.chain_id,
    metadata: api.metadata,
    createdAt: api.created_at,
    icon: api.icon,
    color: api.color as Activity['color'],
    isImportant: api.is_important,
  };
}

function convertTimelineResponse(api: ApiTimelineResponse): TimelineResponse {
  return {
    items: api.items.map(convertActivity),
    total: api.total,
    limit: api.limit,
    offset: api.offset,
    hasMore: api.has_more,
  };
}

function convertStatistics(api: ApiStatistics): ActivityStatistics {
  return {
    totalActivities: api.total_activities,
    activitiesByType: api.activities_by_type,
    activitiesByDay: api.activities_by_day,
    topUsers: api.top_users.map((u) => ({
      userId: u.user_id,
      userName: u.user_name,
      activityCount: u.activity_count,
    })),
    dateRange: api.date_range,
  };
}

// =============================================================================
// API Functions
// =============================================================================

export interface GetMyActivitiesParams {
  limit?: number;
  offset?: number;
  source?: ActivitySource;
  activityType?: string;
  dateFrom?: string;
  dateUntil?: string;
  search?: string;
}

export async function getMyActivities(
  params: GetMyActivitiesParams = {}
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) searchParams.set('limit', params.limit.toString());
  if (params.offset) searchParams.set('offset', params.offset.toString());
  if (params.source) searchParams.set('source', params.source);
  if (params.activityType) searchParams.set('activity_type', params.activityType);
  if (params.dateFrom) searchParams.set('date_from', params.dateFrom);
  if (params.dateUntil) searchParams.set('date_until', params.dateUntil);
  if (params.search) searchParams.set('search', params.search);

  const query = searchParams.toString();
  const url = `/activity/my${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiTimelineResponse>(url);
  return convertTimelineResponse(response);
}

export interface GetTeamTimelineParams {
  teamId: string;
  limit?: number;
  offset?: number;
  activityType?: string;
  dateFrom?: string;
  dateUntil?: string;
}

export async function getTeamTimeline(
  params: GetTeamTimelineParams
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) searchParams.set('limit', params.limit.toString());
  if (params.offset) searchParams.set('offset', params.offset.toString());
  if (params.activityType) searchParams.set('activity_type', params.activityType);
  if (params.dateFrom) searchParams.set('date_from', params.dateFrom);
  if (params.dateUntil) searchParams.set('date_until', params.dateUntil);

  const query = searchParams.toString();
  const url = `/activity/team/${params.teamId}${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiTimelineResponse>(url);
  return convertTimelineResponse(response);
}

export interface GetDocumentTimelineParams {
  documentId: string;
  limit?: number;
  offset?: number;
  activityType?: string;
}

export async function getDocumentTimeline(
  params: GetDocumentTimelineParams
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) searchParams.set('limit', params.limit.toString());
  if (params.offset) searchParams.set('offset', params.offset.toString());
  if (params.activityType) searchParams.set('activity_type', params.activityType);

  const query = searchParams.toString();
  const url = `/activity/document/${params.documentId}${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiTimelineResponse>(url);
  return convertTimelineResponse(response);
}

export interface GetChainTimelineParams {
  chainId: string;
  limit?: number;
  offset?: number;
}

export async function getChainTimeline(
  params: GetChainTimelineParams
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) searchParams.set('limit', params.limit.toString());
  if (params.offset) searchParams.set('offset', params.offset.toString());

  const query = searchParams.toString();
  const url = `/activity/chain/${params.chainId}${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiTimelineResponse>(url);
  return convertTimelineResponse(response);
}

export interface GetCompanyTimelineParams {
  limit?: number;
  offset?: number;
  source?: ActivitySource;
  activityType?: string;
  actorId?: string;
  dateFrom?: string;
  dateUntil?: string;
  search?: string;
}

export async function getCompanyTimeline(
  params: GetCompanyTimelineParams = {}
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (params.limit) searchParams.set('limit', params.limit.toString());
  if (params.offset) searchParams.set('offset', params.offset.toString());
  if (params.source) searchParams.set('source', params.source);
  if (params.activityType) searchParams.set('activity_type', params.activityType);
  if (params.actorId) searchParams.set('actor_id', params.actorId);
  if (params.dateFrom) searchParams.set('date_from', params.dateFrom);
  if (params.dateUntil) searchParams.set('date_until', params.dateUntil);
  if (params.search) searchParams.set('search', params.search);

  const query = searchParams.toString();
  const url = `/activity/company${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiTimelineResponse>(url);
  return convertTimelineResponse(response);
}

export interface GetActivityStatsParams {
  userId?: string;
  teamId?: string;
  dateFrom?: string;
  dateUntil?: string;
}

export async function getActivityStatistics(
  params: GetActivityStatsParams = {}
): Promise<ActivityStatistics> {
  const searchParams = new URLSearchParams();

  if (params.userId) searchParams.set('user_id', params.userId);
  if (params.teamId) searchParams.set('team_id', params.teamId);
  if (params.dateFrom) searchParams.set('date_from', params.dateFrom);
  if (params.dateUntil) searchParams.set('date_until', params.dateUntil);

  const query = searchParams.toString();
  const url = `/activity/stats${query ? `?${query}` : ''}`;

  const { data: response } = await apiClient.get<ApiStatistics>(url);
  return convertStatistics(response);
}

export async function filterTimeline(
  filter: TimelineFilter,
  limit?: number,
  offset?: number
): Promise<TimelineResponse> {
  const searchParams = new URLSearchParams();

  if (limit) searchParams.set('limit', limit.toString());
  if (offset) searchParams.set('offset', offset.toString());

  const query = searchParams.toString();
  const url = `/activity/filter${query ? `?${query}` : ''}`;

  // Convert to snake_case for API
  const body = {
    sources: filter.sources,
    activity_types: filter.activityTypes,
    actor_ids: filter.actorIds,
    target_types: filter.targetTypes,
    date_from: filter.dateFrom,
    date_until: filter.dateUntil,
    search_query: filter.searchQuery,
    important_only: filter.importantOnly,
  };

  const { data: response } = await apiClient.post<ApiTimelineResponse>(url, body);
  return convertTimelineResponse(response);
}
