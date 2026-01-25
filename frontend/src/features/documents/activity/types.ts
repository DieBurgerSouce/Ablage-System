/**
 * Activity Timeline Types
 *
 * TypeScript-Typen fuer das Activity Timeline Feature.
 */

// =============================================================================
// Activity Source & Types
// =============================================================================

export type ActivitySource = 'document' | 'team' | 'chain' | 'workflow' | 'approval' | 'comment' | 'system';

export const ACTIVITY_SOURCE_LABELS: Record<ActivitySource, string> = {
  document: 'Dokument',
  team: 'Team',
  chain: 'Vorgang',
  workflow: 'Workflow',
  approval: 'Genehmigung',
  comment: 'Kommentar',
  system: 'System',
};

export const ACTIVITY_SOURCE_ICONS: Record<ActivitySource, string> = {
  document: 'file-text',
  team: 'users',
  chain: 'link',
  workflow: 'git-branch',
  approval: 'check-square',
  comment: 'message-circle',
  system: 'settings',
};

// =============================================================================
// Activity Colors
// =============================================================================

export type ActivityColor = 'green' | 'red' | 'yellow' | 'blue' | 'purple' | 'gray';

export const ACTIVITY_COLOR_CLASSES: Record<ActivityColor, string> = {
  green: 'bg-green-500',
  red: 'bg-red-500',
  yellow: 'bg-yellow-500',
  blue: 'bg-blue-500',
  purple: 'bg-purple-500',
  gray: 'bg-gray-500',
};

export const ACTIVITY_COLOR_TEXT_CLASSES: Record<ActivityColor, string> = {
  green: 'text-green-600 dark:text-green-400',
  red: 'text-red-600 dark:text-red-400',
  yellow: 'text-yellow-600 dark:text-yellow-400',
  blue: 'text-blue-600 dark:text-blue-400',
  purple: 'text-purple-600 dark:text-purple-400',
  gray: 'text-gray-600 dark:text-gray-400',
};

// =============================================================================
// Activity Models
// =============================================================================

export interface Activity {
  id: string;
  source: ActivitySource;
  activityType: string;
  title: string;
  description?: string | null;

  // Actor
  actorId?: string | null;
  actorName?: string | null;
  actorAvatar?: string | null;

  // Target
  targetType?: string | null;
  targetId?: string | null;
  targetName?: string | null;

  // Related
  relatedType?: string | null;
  relatedId?: string | null;
  relatedName?: string | null;

  // Context
  companyId?: string | null;
  teamId?: string | null;
  chainId?: string | null;

  // Metadata
  metadata: Record<string, unknown>;

  // Timestamps
  createdAt: string;

  // Display
  icon?: string | null;
  color?: ActivityColor | null;
  isImportant: boolean;
}

export interface TimelineResponse {
  items: Activity[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

// =============================================================================
// Filter Types
// =============================================================================

export interface TimelineFilter {
  sources?: ActivitySource[];
  activityTypes?: string[];
  actorIds?: string[];
  targetTypes?: string[];
  dateFrom?: string;
  dateUntil?: string;
  searchQuery?: string;
  importantOnly?: boolean;
}

// =============================================================================
// Statistics Types
// =============================================================================

export interface ActivityStatistics {
  totalActivities: number;
  activitiesByType: Record<string, number>;
  activitiesByDay: Array<{
    date: string | null;
    count: number;
  }>;
  topUsers: Array<{
    userId: string;
    userName: string;
    activityCount: number;
  }>;
  dateRange: {
    from: string;
    until: string;
  };
}

// =============================================================================
// Activity Type Labels (German)
// =============================================================================

export const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  // Document Activities
  document_created: 'Dokument erstellt',
  document_uploaded: 'Dokument hochgeladen',
  document_viewed: 'Dokument angesehen',
  document_downloaded: 'Dokument heruntergeladen',
  document_edited: 'Dokument bearbeitet',
  document_deleted: 'Dokument geloescht',
  document_archived: 'Dokument archiviert',
  document_restored: 'Dokument wiederhergestellt',
  document_shared: 'Dokument geteilt',
  document_moved: 'Dokument verschoben',

  // OCR Activities
  ocr_started: 'OCR gestartet',
  ocr_completed: 'OCR abgeschlossen',
  ocr_failed: 'OCR fehlgeschlagen',

  // Approval Activities
  approval_requested: 'Genehmigung angefordert',
  approval_granted: 'Genehmigung erteilt',
  approval_rejected: 'Genehmigung abgelehnt',

  // Comment Activities
  comment_added: 'Kommentar hinzugefuegt',

  // Tag Activities
  tag_added: 'Tag hinzugefuegt',
  tag_removed: 'Tag entfernt',

  // Team Activities
  member_joined: 'Mitglied beigetreten',
  member_left: 'Mitglied ausgetreten',
  member_role_changed: 'Rolle geaendert',
  team_created: 'Team erstellt',
  team_updated: 'Team aktualisiert',
  team_archived: 'Team archiviert',
  invitation_sent: 'Einladung gesendet',
  invitation_accepted: 'Einladung angenommen',
  invitation_declined: 'Einladung abgelehnt',
};

export function getActivityTypeLabel(activityType: string): string {
  return ACTIVITY_TYPE_LABELS[activityType] || activityType;
}
