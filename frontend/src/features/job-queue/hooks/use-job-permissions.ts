/**
 * Job Queue Permission Hook
 *
 * Rollenbasierte Zugriffssteuerung für Job Queue.
 * Definiert welche Aktionen der User ausführen darf.
 */

import { useMemo } from 'react';
import { useAuth } from '@/lib/auth/AuthContext';

// ==================== Types ====================

export interface JobQueuePermissions {
  /** Kann die Job Queue Seite sehen */
  canView: boolean;
  /** Kann Jobs verwalten (cancel, retry, etc.) */
  canManage: boolean;
  /** Kann Job-Prioritäten ändern */
  canChangePriority: boolean;
  /** Kann Jobs pausieren/fortsetzen */
  canPauseResume: boolean;
  /** Kann Bulk-Aktionen ausführen */
  canBulkActions: boolean;
  /** Kann Warteschlange leeren */
  canClearQueue: boolean;
  /** Kann Force-Kill ausführen */
  canForceKill: boolean;
  /** Kann DLQ verwalten */
  canManageDLQ: boolean;
  /** Kann DLQ leeren */
  canPurgeDLQ: boolean;
  /** Kann Worker-Status sehen */
  canViewWorkers: boolean;
  /** Kann GPU-Status sehen */
  canViewGPU: boolean;
  /** Kann System-Health sehen */
  canViewHealth: boolean;
  /** Kann Benachrichtigungseinstellungen ändern */
  canConfigureNotifications: boolean;
}

// ==================== Constants ====================

/**
 * Permissions required for job queue access.
 */
export const JOB_QUEUE_PERMISSIONS = {
  VIEW: 'job_queue.view',
  MANAGE: 'job_queue.manage',
  ADMIN: 'job_queue.admin',
} as const;

// ==================== Hook ====================

/**
 * Hook für Job Queue Berechtigungen.
 *
 * Berechtigungen basieren auf:
 * - is_superuser: Voller Zugriff auf alles
 * - admin role: Voller Zugriff auf alles
 * - editor role: Eingeschränkter Zugriff (view + basic manage)
 * - viewer role: Nur Ansicht
 */
export function useJobPermissions(): JobQueuePermissions {
  const { user } = useAuth();

  return useMemo(() => {
    // Nicht eingeloggt = keine Berechtigungen
    if (!user) {
      return {
        canView: false,
        canManage: false,
        canChangePriority: false,
        canPauseResume: false,
        canBulkActions: false,
        canClearQueue: false,
        canForceKill: false,
        canManageDLQ: false,
        canPurgeDLQ: false,
        canViewWorkers: false,
        canViewGPU: false,
        canViewHealth: false,
        canConfigureNotifications: false,
      };
    }

    const isSuperuser = user.is_superuser;
    const isAdmin = user.role === 'admin' || isSuperuser;

    return {
      // Nur Admins und Superuser können die Job Queue sehen
      canView: isAdmin,

      // Admins können Jobs verwalten
      canManage: isAdmin,

      // Admins können Prioritäten ändern
      canChangePriority: isAdmin,

      // Admins können pausieren/fortsetzen
      canPauseResume: isAdmin,

      // Admins können Bulk-Aktionen ausführen
      canBulkActions: isAdmin,

      // Nur Superuser können die Warteschlange leeren
      canClearQueue: isSuperuser,

      // Nur Superuser können Force-Kill ausführen
      canForceKill: isSuperuser,

      // Admins können DLQ verwalten
      canManageDLQ: isAdmin,

      // Nur Superuser können DLQ leeren
      canPurgeDLQ: isSuperuser,

      // Admins können Worker-Status sehen
      canViewWorkers: isAdmin,

      // Admins können GPU-Status sehen
      canViewGPU: isAdmin,

      // Admins können System-Health sehen
      canViewHealth: isAdmin,

      // Alle mit View-Zugriff können Notifications konfigurieren
      canConfigureNotifications: isAdmin,
    };
  }, [user]);
}

// ==================== Utility Functions ====================

/**
 * Prüft ob der User die Job Queue Seite sehen darf.
 * Nutze dies für Route Protection.
 */
export function canAccessJobQueue(user: { is_superuser: boolean; role: string } | null): boolean {
  if (!user) return false;
  return user.is_superuser || user.role === 'admin';
}

/**
 * Gibt eine Nachricht zurück warum der Zugriff verweigert wurde.
 */
export function getAccessDeniedMessage(): string {
  return 'Sie haben keine Berechtigung, die Job Queue zu verwalten. Bitte wenden Sie sich an einen Administrator.';
}

export default useJobPermissions;
