/**
 * Workflow Versions API Service
 *
 * API Client für Workflow-Versionierung, A/B Testing und Rollback.
 */

import { apiClient } from '../client';
import type {
  WorkflowVersion,
  WorkflowABTest,
  VersionDiff,
  CreateVersionRequest,
  CreateABTestRequest,
  RollbackRequest,
  VersionListResponse,
  VersionListParams,
  VersionComparisonItem,
} from '@/features/workflows/versioning/types/version-types';

const BASE_URL = '/workflows';

// =============================================================================
// VERSION CRUD
// =============================================================================

/**
 * Listet alle Versionen eines Workflows.
 */
export async function listVersions(
  workflowId: string,
  params: VersionListParams = {}
): Promise<VersionListResponse> {
  const response = await apiClient.get<VersionListResponse>(
    `${BASE_URL}/${workflowId}/versions`,
    { params }
  );
  return response.data;
}

/**
 * Ruft eine Version nach ID ab.
 */
export async function getVersion(
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  const response = await apiClient.get<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/versions/${versionId}`
  );
  return response.data;
}

/**
 * Ruft die aktive Version eines Workflows ab.
 */
export async function getActiveVersion(
  workflowId: string
): Promise<WorkflowVersion | null> {
  const response = await apiClient.get<WorkflowVersion | null>(
    `${BASE_URL}/${workflowId}/versions/active`
  );
  return response.data;
}

/**
 * Erstellt eine neue Version.
 */
export async function createVersion(
  workflowId: string,
  data: CreateVersionRequest
): Promise<WorkflowVersion> {
  const response = await apiClient.post<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/versions`,
    data
  );
  return response.data;
}

/**
 * Veröffentlicht eine Draft-Version.
 */
export async function publishVersion(
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  const response = await apiClient.post<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/versions/${versionId}/publish`
  );
  return response.data;
}

/**
 * Markiert eine Version als veraltet.
 */
export async function deprecateVersion(
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  const response = await apiClient.post<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/versions/${versionId}/deprecate`
  );
  return response.data;
}

/**
 * Archiviert eine Version.
 */
export async function archiveVersion(
  workflowId: string,
  versionId: string
): Promise<WorkflowVersion> {
  const response = await apiClient.post<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/versions/${versionId}/archive`
  );
  return response.data;
}

// =============================================================================
// DIFF & COMPARISON
// =============================================================================

/**
 * Berechnet den Diff zwischen zwei Versionen.
 */
export async function getVersionDiff(
  workflowId: string,
  versionId: string,
  compareToId?: string
): Promise<VersionDiff> {
  const response = await apiClient.get<VersionDiff>(
    `${BASE_URL}/${workflowId}/versions/${versionId}/diff`,
    { params: { compare_to_id: compareToId } }
  );
  return response.data;
}

/**
 * Vergleicht mehrere Versionen nach Statistiken.
 */
export async function compareVersions(
  workflowId: string,
  versionIds?: string[]
): Promise<VersionComparisonItem[]> {
  const response = await apiClient.get<VersionComparisonItem[]>(
    `${BASE_URL}/${workflowId}/versions/compare`,
    { params: { version_ids: versionIds?.join(',') } }
  );
  return response.data;
}

// =============================================================================
// ROLLBACK
// =============================================================================

/**
 * Rollt einen Workflow auf eine vorherige Version zurück.
 */
export async function rollbackToVersion(
  workflowId: string,
  data: RollbackRequest
): Promise<WorkflowVersion> {
  const response = await apiClient.post<WorkflowVersion>(
    `${BASE_URL}/${workflowId}/rollback`,
    data
  );
  return response.data;
}

// =============================================================================
// A/B TESTING
// =============================================================================

/**
 * Erstellt einen neuen A/B Test.
 */
export async function createABTest(
  workflowId: string,
  data: CreateABTestRequest
): Promise<WorkflowABTest> {
  const response = await apiClient.post<WorkflowABTest>(
    `${BASE_URL}/${workflowId}/ab-tests`,
    data
  );
  return response.data;
}

/**
 * Listet alle A/B Tests eines Workflows.
 */
export async function listABTests(
  workflowId: string
): Promise<WorkflowABTest[]> {
  const response = await apiClient.get<WorkflowABTest[]>(
    `${BASE_URL}/${workflowId}/ab-tests`
  );
  return response.data;
}

/**
 * Ruft einen A/B Test ab.
 */
export async function getABTest(
  workflowId: string,
  testId: string
): Promise<WorkflowABTest> {
  const response = await apiClient.get<WorkflowABTest>(
    `${BASE_URL}/${workflowId}/ab-tests/${testId}`
  );
  return response.data;
}

/**
 * Startet einen A/B Test.
 */
export async function startABTest(
  workflowId: string,
  testId: string
): Promise<WorkflowABTest> {
  const response = await apiClient.post<WorkflowABTest>(
    `${BASE_URL}/${workflowId}/ab-tests/${testId}/start`
  );
  return response.data;
}

/**
 * Beendet einen A/B Test.
 */
export async function stopABTest(
  workflowId: string,
  testId: string,
  winner?: 'control' | 'treatment' | 'inconclusive'
): Promise<WorkflowABTest> {
  const response = await apiClient.post<WorkflowABTest>(
    `${BASE_URL}/${workflowId}/ab-tests/${testId}/stop`,
    { winner }
  );
  return response.data;
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

/**
 * Formatiert den Versions-Status für die Anzeige.
 */
export function formatVersionStatus(status: string): string {
  switch (status) {
    case 'draft':
      return 'Entwurf';
    case 'active':
      return 'Aktiv';
    case 'deprecated':
      return 'Veraltet';
    case 'rolled_back':
      return 'Zurückgerollt';
    case 'archived':
      return 'Archiviert';
    default:
      return status;
  }
}

/**
 * Gibt die Badge-Variante für den Status zurück.
 */
export function getVersionStatusVariant(
  status: string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'active':
      return 'default';
    case 'draft':
      return 'secondary';
    case 'deprecated':
    case 'rolled_back':
      return 'destructive';
    case 'archived':
      return 'outline';
    default:
      return 'outline';
  }
}

/**
 * Formatiert den A/B Test Status für die Anzeige.
 */
export function formatABTestStatus(status: string): string {
  switch (status) {
    case 'draft':
      return 'Entwurf';
    case 'running':
      return 'Läuft';
    case 'completed':
      return 'Abgeschlossen';
    case 'cancelled':
      return 'Abgebrochen';
    default:
      return status;
  }
}

/**
 * Formatiert den Change-Type für die Anzeige.
 */
export function formatChangeType(changeType: string): string {
  switch (changeType) {
    case 'major':
      return 'Major';
    case 'minor':
      return 'Minor';
    case 'patch':
      return 'Patch';
    default:
      return changeType;
  }
}
