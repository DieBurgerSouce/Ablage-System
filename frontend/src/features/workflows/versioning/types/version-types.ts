/**
 * Workflow Versioning Types
 *
 * TypeScript-Definitionen fuer Workflow-Versionierung.
 */

// =============================================================================
// VERSION STATUS
// =============================================================================

export type VersionStatus = 'draft' | 'active' | 'deprecated' | 'rolled_back' | 'archived';

export type ABTestStatus = 'draft' | 'running' | 'completed' | 'cancelled';

export type ChangeType = 'major' | 'minor' | 'patch';

// =============================================================================
// WORKFLOW VERSION
// =============================================================================

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  company_id: string;
  version: string;
  major: number;
  minor: number;
  patch: number;
  status: VersionStatus;
  is_active: boolean;
  is_latest: boolean;
  definition: WorkflowDefinition;
  change_description: string;
  change_type: ChangeType;
  parent_version_id: string | null;
  diff_summary: DiffSummary | null;
  execution_count: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_execution_time_ms: number | null;
  created_by_id: string;
  created_at: string;
  published_at: string | null;
  deprecated_at: string | null;
  archived_at: string | null;
}

export interface WorkflowDefinition {
  name: string;
  description?: string | null;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: Record<string, unknown>;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    sourceHandle?: string;
    targetHandle?: string;
    label?: string;
  }>;
  variables: Record<string, unknown>;
  max_concurrent_executions?: number;
  timeout_seconds?: number;
  retry_config?: Record<string, unknown>;
}

export interface DiffSummary {
  added: string[];
  removed: string[];
  modified: string[];
}

export interface DiffDetails {
  nodes?: {
    added: string[];
    removed: string[];
    modified: string[];
  };
  edges?: {
    added: string[];
    removed: string[];
    modified: string[];
  };
  trigger_config?: DiffSummary;
}

export interface VersionDiff {
  version_a: string | null;
  version_b: string;
  changes: DiffSummary;
  details: DiffDetails;
}

// =============================================================================
// A/B TEST
// =============================================================================

export interface WorkflowABTest {
  id: string;
  workflow_id: string;
  company_id: string;
  name: string;
  description: string | null;
  control_version_id: string;
  treatment_version_id: string;
  treatment_percentage: number;
  status: ABTestStatus;
  winner: string | null;
  control_executions: number;
  control_successes: number;
  control_failures: number;
  control_success_rate: number;
  control_avg_time_ms: number | null;
  treatment_executions: number;
  treatment_successes: number;
  treatment_failures: number;
  treatment_success_rate: number;
  treatment_avg_time_ms: number | null;
  start_at: string | null;
  end_at: string | null;
  completed_at: string | null;
  created_by_id: string;
  created_at: string;
}

// =============================================================================
// API REQUESTS
// =============================================================================

export interface CreateVersionRequest {
  change_description: string;
  change_type: ChangeType;
  definition?: WorkflowDefinition;
}

export interface CreateABTestRequest {
  name: string;
  description?: string;
  control_version_id: string;
  treatment_version_id: string;
  treatment_percentage?: number;
  end_at?: string;
}

export interface RollbackRequest {
  target_version_id: string;
  create_backup?: boolean;
}

// =============================================================================
// API RESPONSES
// =============================================================================

export interface VersionListResponse {
  items: WorkflowVersion[];
  total: number;
}

export interface VersionComparisonItem {
  version_id: string;
  version: string;
  status: VersionStatus;
  is_active: boolean;
  execution_count: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  avg_execution_time_ms: number | null;
  created_at: string | null;
  published_at: string | null;
}

// =============================================================================
// QUERY PARAMS
// =============================================================================

export interface VersionListParams {
  status?: VersionStatus;
  offset?: number;
  limit?: number;
}
