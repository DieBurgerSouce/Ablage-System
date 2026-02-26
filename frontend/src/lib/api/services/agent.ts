/**
 * KI-Agent Orchestrator API Service
 *
 * Stellt Zugriff auf den intelligenten Multi-Agent-Orchestrator bereit:
 * - Abfragen mit sichtbarer Chain-of-Thought (CoT)
 * - Schnellanfragen mit minimalem Kontext
 * - Auflistung verfuegbarer Sub-Agenten
 * - Orchestrator-Statusabfrage
 */

import { apiClient } from '../client';

// ===== Types =====

/**
 * Sichtbarer Chain-of-Thought-Schritt eines Sub-Agenten
 */
export interface ThinkingStep {
  /** Eindeutige ID des Denkschritts */
  id: string;
  /** Typ des ausfuehrenden Agenten */
  agent_type: 'document' | 'matching' | 'compliance' | 'finance' | 'anomaly' | 'search' | 'general';
  /** Anzeigename des Agenten */
  agent_name: string;
  /** Beschreibung der aktuellen Aufgabe */
  description: string;
  /** Ausfuehrungsstatus des Schritts */
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  /** Liste von Detailangaben zum Schritt */
  details: string[];
  /** Kurzzusammenfassung des Ergebnisses, falls abgeschlossen */
  result_summary: string | null;
  /** ISO-8601-Zeitstempel des Starts */
  started_at: string | null;
  /** ISO-8601-Zeitstempel des Abschlusses */
  completed_at: string | null;
  /** Dauer in Millisekunden */
  duration_ms: number | null;
  /** Fehlermeldung bei Status 'failed' */
  error: string | null;
}

/**
 * Vorgeschlagene Aktion als Button fuer die Benutzeroberflaeche
 */
export interface SuggestedAction {
  /** Beschriftung des Aktions-Buttons */
  label: string;
  /** Typ der auszufuehrenden Aktion */
  action_type: string;
  /** Aktionsparameter */
  params: Record<string, unknown>;
  /** Darstellungsvariante des Buttons */
  variant: 'default' | 'outline' | 'ghost' | 'destructive';
}

/**
 * Antwort auf eine vollstaendige Agent-Abfrage mit CoT-Daten
 */
export interface AgentQueryResponse {
  /** Generierte Antwort des Orchestrators */
  answer: string;
  /** Alle sichtbaren Denkschritte */
  thinking_steps: ThinkingStep[];
  /** Vorgeschlagene Folgeaktionen */
  suggested_actions: SuggestedAction[];
  /** ID des Gespraechsverlaufs, sofern vorhanden */
  conversation_id: string | null;
  /** Gesamtdauer der Verarbeitung in Millisekunden */
  total_duration_ms: number;
  /** Verwendetes Sprachmodell */
  model_used: string | null;
}

/**
 * Informationen zu einem registrierten Sub-Agenten
 */
export interface SubAgentInfo {
  /** Interner Agentenbezeichner */
  agent_type: string;
  /** Anzeigename des Agenten */
  display_name: string;
  /** Beschreibung der Agentenfunktion */
  description: string;
  /** Liste der Faehigkeiten */
  capabilities: string[];
}

/**
 * Betriebsstatus des Orchestrators
 */
export interface OrchestratorStatus {
  /** Aktueller Systemstatus */
  status: 'operational' | 'degraded' | 'offline';
  /** Anzahl der registrierten Sub-Agenten */
  registered_agents: number;
  /** Liste der verfuegbaren Sub-Agenten */
  agents: SubAgentInfo[];
  /** Gibt an, ob ein Sprachmodell verfuegbar ist */
  llm_available: boolean;
  /** Standardanbieter des Sprachmodells */
  default_provider: string;
}

// ===== Interne Request-Typen =====

interface AgentQueryRequest {
  query: string;
  context?: Record<string, unknown>;
  conversation_id?: string;
}

interface QuickAskRequest {
  query: string;
  document_id?: string;
  page_context?: string;
}

// ===== API-Funktionen =====

/**
 * Sendet eine vollstaendige Abfrage an den KI-Orchestrator.
 *
 * Die Antwort enthaelt sichtbare Chain-of-Thought-Schritte aller
 * beteiligten Sub-Agenten sowie vorgeschlagene Folgeaktionen.
 *
 * @param query - Die Anfrage des Benutzers
 * @param context - Optionaler zusaetzlicher Kontext (z. B. aktuelle Seite, Filter)
 * @param conversationId - Optionale ID fuer Gespraechskontinuitaet
 * @returns Vollstaendige Orchestrator-Antwort mit CoT-Daten
 */
export async function agentQuery(
  query: string,
  context?: Record<string, unknown>,
  conversationId?: string,
): Promise<AgentQueryResponse> {
  const payload: AgentQueryRequest = { query };
  if (context !== undefined) {
    payload.context = context;
  }
  if (conversationId !== undefined) {
    payload.conversation_id = conversationId;
  }
  const response = await apiClient.post<AgentQueryResponse>('/agent/query', payload);
  return response.data;
}

/**
 * Sendet eine Schnellanfrage mit minimalem Kontext an den Orchestrator.
 *
 * Geeignet fuer kurze, kontextarme Anfragen ohne vollstaendige CoT-Verarbeitung.
 *
 * @param query - Die Anfrage des Benutzers
 * @param documentId - Optionale Dokument-ID fuer dokumentbezogene Anfragen
 * @param pageContext - Optionaler Seitenkontext (z. B. aktuell angezeigte Seite)
 * @returns Kompakte Orchestrator-Antwort
 */
export async function quickAsk(
  query: string,
  documentId?: string,
  pageContext?: string,
): Promise<AgentQueryResponse> {
  const payload: QuickAskRequest = { query };
  if (documentId !== undefined) {
    payload.document_id = documentId;
  }
  if (pageContext !== undefined) {
    payload.page_context = pageContext;
  }
  const response = await apiClient.post<AgentQueryResponse>('/agent/quick-ask', payload);
  return response.data;
}

/**
 * Ruft die Liste aller beim Orchestrator registrierten Sub-Agenten ab.
 *
 * @returns Array mit Informationen zu jedem verfuegbaren Sub-Agenten
 */
export async function listAgents(): Promise<SubAgentInfo[]> {
  const response = await apiClient.get<SubAgentInfo[]>('/agent/agents');
  return response.data;
}

/**
 * Ruft den aktuellen Betriebsstatus des Orchestrators ab.
 *
 * Gibt Auskunft ueber Verfuegbarkeit, Anzahl der Agenten und
 * den Status des konfigurierten Sprachmodells.
 *
 * @returns Aktueller Orchestrator-Status
 */
export async function getAgentStatus(): Promise<OrchestratorStatus> {
  const response = await apiClient.get<OrchestratorStatus>('/agent/status');
  return response.data;
}
