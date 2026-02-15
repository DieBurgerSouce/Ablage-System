/**
 * API Service for Approval Enhanced
 */

import { apiClient } from '@/lib/api/client';
import {
  ConditionalRuleBackend,
  EscalationRuleBackend,
  SubstitutionRuleBackend,
  SLAMetricsBackend,
  SLAReportBackend,
  AutoFileStatsBackend,
  AutoMatchResultBackend,
  CreateConditionalRuleDTO,
  UpdateConditionalRuleDTO,
  CreateEscalationRuleDTO,
  CreateSubstitutionRuleDTO,
} from '../types/approval-enhanced-types';

const BASE_PATH = '/approval-enhanced';

// ==================== Conditional Rules ====================

export async function getConditionalRules(): Promise<ConditionalRuleBackend[]> {
  try {
    const response = await apiClient.get<ConditionalRuleBackend[]>(`${BASE_PATH}/conditional-rules`);
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der bedingten Regeln:', error);
    throw new Error('Bedingte Regeln konnten nicht geladen werden');
  }
}

export async function createConditionalRule(
  data: CreateConditionalRuleDTO
): Promise<ConditionalRuleBackend> {
  try {
    const response = await apiClient.post<ConditionalRuleBackend>(
      `${BASE_PATH}/conditional-rules`,
      data
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Erstellen der bedingten Regel:', error);
    throw new Error('Bedingte Regel konnte nicht erstellt werden');
  }
}

export async function updateConditionalRule(
  ruleId: number,
  data: UpdateConditionalRuleDTO
): Promise<ConditionalRuleBackend> {
  try {
    const response = await apiClient.put<ConditionalRuleBackend>(
      `${BASE_PATH}/conditional-rules/${ruleId}`,
      data
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Aktualisieren der bedingten Regel:', error);
    throw new Error('Bedingte Regel konnte nicht aktualisiert werden');
  }
}

export async function deleteConditionalRule(ruleId: number): Promise<void> {
  try {
    await apiClient.delete(`${BASE_PATH}/conditional-rules/${ruleId}`);
  } catch (error) {
    console.error('Fehler beim Löschen der bedingten Regel:', error);
    throw new Error('Bedingte Regel konnte nicht gelöscht werden');
  }
}

// ==================== Escalation Rules ====================

export async function getEscalationRules(): Promise<EscalationRuleBackend[]> {
  try {
    const response = await apiClient.get<EscalationRuleBackend[]>(`${BASE_PATH}/escalation-rules`);
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der Eskalationsregeln:', error);
    throw new Error('Eskalationsregeln konnten nicht geladen werden');
  }
}

export async function createEscalationRule(
  data: CreateEscalationRuleDTO
): Promise<EscalationRuleBackend> {
  try {
    const response = await apiClient.post<EscalationRuleBackend>(
      `${BASE_PATH}/escalation-rules`,
      data
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Erstellen der Eskalationsregel:', error);
    throw new Error('Eskalationsregel konnte nicht erstellt werden');
  }
}

export async function deleteEscalationRule(ruleId: number): Promise<void> {
  try {
    await apiClient.delete(`${BASE_PATH}/escalation-rules/${ruleId}`);
  } catch (error) {
    console.error('Fehler beim Löschen der Eskalationsregel:', error);
    throw new Error('Eskalationsregel konnte nicht gelöscht werden');
  }
}

// ==================== Substitution Rules ====================

export async function getSubstitutionRules(): Promise<SubstitutionRuleBackend[]> {
  try {
    const response = await apiClient.get<SubstitutionRuleBackend[]>(
      `${BASE_PATH}/substitution-rules`
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der Stellvertretungen:', error);
    throw new Error('Stellvertretungen konnten nicht geladen werden');
  }
}

export async function createSubstitutionRule(
  data: CreateSubstitutionRuleDTO
): Promise<SubstitutionRuleBackend> {
  try {
    const response = await apiClient.post<SubstitutionRuleBackend>(
      `${BASE_PATH}/substitution-rules`,
      data
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Erstellen der Stellvertretung:', error);
    throw new Error('Stellvertretung konnte nicht erstellt werden');
  }
}

export async function deleteSubstitutionRule(ruleId: number): Promise<void> {
  try {
    await apiClient.delete(`${BASE_PATH}/substitution-rules/${ruleId}`);
  } catch (error) {
    console.error('Fehler beim Löschen der Stellvertretung:', error);
    throw new Error('Stellvertretung konnte nicht gelöscht werden');
  }
}

// ==================== SLA Metrics ====================

export async function getSLAMetrics(): Promise<SLAMetricsBackend> {
  try {
    const response = await apiClient.get<SLAMetricsBackend>(`${BASE_PATH}/sla/metrics`);
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der SLA-Metriken:', error);
    throw new Error('SLA-Metriken konnten nicht geladen werden');
  }
}

export async function getSLAReport(
  startDate?: string,
  endDate?: string
): Promise<SLAReportBackend> {
  try {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    const response = await apiClient.get<SLAReportBackend>(
      `${BASE_PATH}/sla/report?${params.toString()}`
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden des SLA-Berichts:', error);
    throw new Error('SLA-Bericht konnte nicht geladen werden');
  }
}

// ==================== Auto-Filing ====================

export async function triggerAutoFile(): Promise<void> {
  try {
    await apiClient.post(`${BASE_PATH}/auto-file`);
  } catch (error) {
    console.error('Fehler beim Auslösen der automatischen Ablage:', error);
    throw new Error('Automatische Ablage konnte nicht ausgelöst werden');
  }
}

export async function getAutoFileStats(): Promise<AutoFileStatsBackend> {
  try {
    const response = await apiClient.get<AutoFileStatsBackend>(`${BASE_PATH}/auto-file/stats`);
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der Ablage-Statistiken:', error);
    throw new Error('Ablage-Statistiken konnten nicht geladen werden');
  }
}

// ==================== Auto-Matching ====================

export async function triggerAutoMatch(documentId: number): Promise<void> {
  try {
    await apiClient.post(`${BASE_PATH}/auto-match`, { document_id: documentId });
  } catch (error) {
    console.error('Fehler beim Auslösen der automatischen Zuordnung:', error);
    throw new Error('Automatische Zuordnung konnte nicht ausgelöst werden');
  }
}

export async function getAutoMatchResults(documentId: number): Promise<AutoMatchResultBackend> {
  try {
    const response = await apiClient.get<AutoMatchResultBackend>(
      `${BASE_PATH}/auto-match/results?document_id=${documentId}`
    );
    return response.data;
  } catch (error) {
    console.error('Fehler beim Laden der Zuordnungsergebnisse:', error);
    throw new Error('Zuordnungsergebnisse konnten nicht geladen werden');
  }
}
