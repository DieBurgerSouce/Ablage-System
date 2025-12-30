/**
 * Permission Hook fuer rollenbasierte Zugriffskontrolle
 *
 * Bietet eine einfache API zur Ueberpruefung von Benutzerberechtigungen
 * basierend auf Rolle und Superuser-Status.
 *
 * Verwendung:
 *   const { hasPermission, hasAnyPermission, canAccess } = usePermissions();
 *
 *   if (hasPermission('validation:write')) {
 *     // Zeige Validierungsbutton
 *   }
 */

import { useMemo } from 'react';
import { useAuth } from '../AuthContext';

// Permission-Definitionen basierend auf Rollen
const ROLE_PERMISSIONS: Record<string, string[]> = {
  admin: [
    'documents:read',
    'documents:write',
    'documents:delete',
    'documents:manage',
    'validation:read',
    'validation:write',
    'validation:manage',
    'training:read',
    'training:write',
    'training:manage',
    'users:read',
    'users:write',
    'users:manage',
    'system:read',
    'system:manage',
    'backup:read',
    'backup:write',
  ],
  editor: [
    'documents:read',
    'documents:write',
    'validation:read',
    'validation:write',
    'training:read',
    'training:write',
  ],
  viewer: [
    'documents:read',
    'validation:read',
    'training:read',
  ],
};

// Superuser hat alle Berechtigungen
const ALL_PERMISSIONS = [
  ...new Set(Object.values(ROLE_PERMISSIONS).flat()),
];

export interface PermissionHookResult {
  /**
   * Prueft ob der Benutzer eine bestimmte Berechtigung hat.
   */
  hasPermission: (permission: string) => boolean;

  /**
   * Prueft ob der Benutzer mindestens eine der angegebenen Berechtigungen hat.
   */
  hasAnyPermission: (...permissions: string[]) => boolean;

  /**
   * Prueft ob der Benutzer alle angegebenen Berechtigungen hat.
   */
  hasAllPermissions: (...permissions: string[]) => boolean;

  /**
   * Prueft ob der Benutzer Zugriff auf ein bestimmtes Feature hat.
   */
  canAccess: {
    validation: boolean;
    validationManage: boolean;
    training: boolean;
    trainingManage: boolean;
    admin: boolean;
    users: boolean;
    system: boolean;
    backup: boolean;
  };

  /**
   * Benutzerrollen
   */
  isAdmin: boolean;
  isEditor: boolean;
  isViewer: boolean;
  isSuperuser: boolean;
}

export function usePermissions(): PermissionHookResult {
  const { user } = useAuth();

  const permissions = useMemo(() => {
    if (!user) {
      return [];
    }

    // Superuser hat alle Berechtigungen
    if (user.is_superuser) {
      return ALL_PERMISSIONS;
    }

    // Sonst basierend auf Rolle
    const role = user.role || 'viewer';
    return ROLE_PERMISSIONS[role] || ROLE_PERMISSIONS.viewer;
  }, [user]);

  const hasPermission = useMemo(() => {
    return (permission: string): boolean => {
      if (!user) return false;
      if (user.is_superuser) return true;
      return permissions.includes(permission);
    };
  }, [user, permissions]);

  const hasAnyPermission = useMemo(() => {
    return (...perms: string[]): boolean => {
      if (!user) return false;
      if (user.is_superuser) return true;
      return perms.some((p) => permissions.includes(p));
    };
  }, [user, permissions]);

  const hasAllPermissions = useMemo(() => {
    return (...perms: string[]): boolean => {
      if (!user) return false;
      if (user.is_superuser) return true;
      return perms.every((p) => permissions.includes(p));
    };
  }, [user, permissions]);

  const canAccess = useMemo(() => ({
    validation: hasPermission('validation:read'),
    validationManage: hasPermission('validation:manage'),
    training: hasPermission('training:read'),
    trainingManage: hasPermission('training:manage'),
    admin: hasPermission('users:manage'),
    users: hasPermission('users:read'),
    system: hasPermission('system:read'),
    backup: hasPermission('backup:read'),
  }), [hasPermission]);

  const isAdmin = user?.is_superuser || user?.role === 'admin';
  const isEditor = user?.role === 'editor';
  const isViewer = user?.role === 'viewer';
  const isSuperuser = user?.is_superuser || false;

  return {
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canAccess,
    isAdmin: isAdmin || false,
    isEditor: isEditor || false,
    isViewer: isViewer || false,
    isSuperuser,
  };
}

export default usePermissions;
