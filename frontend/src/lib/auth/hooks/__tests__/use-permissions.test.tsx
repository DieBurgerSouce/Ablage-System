/**
 * usePermissions Hook Unit Tests
 *
 * Enterprise-Level Tests für das Permission-Hook.
 * Testet rollenbasierte Zugriffskontrolle (RBAC).
 */

import { renderHook } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { usePermissions } from '../use-permissions';

// Mock the AuthContext
const mockUser = vi.fn();

vi.mock('../../AuthContext', () => ({
    useAuth: () => ({
        user: mockUser(),
    }),
}));

describe('usePermissions', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUser.mockReturnValue(null);
    });

    // ==================== Kein User (Logged Out) ====================

    describe('ohne authentifizierten User', () => {
        it('gibt false für alle Berechtigungen zurück', () => {
            mockUser.mockReturnValue(null);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:read')).toBe(false);
            expect(result.current.hasPermission('users:manage')).toBe(false);
        });

        it('gibt false für hasAnyPermission zurück', () => {
            mockUser.mockReturnValue(null);

            const { result } = renderHook(() => usePermissions());

            expect(
                result.current.hasAnyPermission('documents:read', 'documents:write')
            ).toBe(false);
        });

        it('gibt false für hasAllPermissions zurück', () => {
            mockUser.mockReturnValue(null);

            const { result } = renderHook(() => usePermissions());

            expect(
                result.current.hasAllPermissions('documents:read', 'documents:write')
            ).toBe(false);
        });

        it('setzt alle canAccess Flags auf false', () => {
            mockUser.mockReturnValue(null);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.validation).toBe(false);
            expect(result.current.canAccess.training).toBe(false);
            expect(result.current.canAccess.admin).toBe(false);
            expect(result.current.canAccess.system).toBe(false);
            expect(result.current.canAccess.backup).toBe(false);
        });

        it('setzt alle Rollen-Flags auf false', () => {
            mockUser.mockReturnValue(null);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.isAdmin).toBe(false);
            expect(result.current.isEditor).toBe(false);
            expect(result.current.isViewer).toBe(false);
            expect(result.current.isSuperuser).toBe(false);
        });
    });

    // ==================== Viewer Role ====================

    describe('Viewer Rolle', () => {
        const viewerUser = {
            id: '1',
            email: 'viewer@test.com',
            role: 'viewer',
            is_superuser: false,
        };

        it('hat Leserechte für Dokumente', () => {
            mockUser.mockReturnValue(viewerUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:read')).toBe(true);
        });

        it('hat keine Schreibrechte für Dokumente', () => {
            mockUser.mockReturnValue(viewerUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:write')).toBe(false);
            expect(result.current.hasPermission('documents:delete')).toBe(false);
            expect(result.current.hasPermission('documents:manage')).toBe(false);
        });

        it('kann validation und training lesen', () => {
            mockUser.mockReturnValue(viewerUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.validation).toBe(true);
            expect(result.current.canAccess.training).toBe(true);
            expect(result.current.canAccess.validationManage).toBe(false);
            expect(result.current.canAccess.trainingManage).toBe(false);
        });

        it('hat keinen Admin-Zugriff', () => {
            mockUser.mockReturnValue(viewerUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.admin).toBe(false);
            expect(result.current.canAccess.system).toBe(false);
            expect(result.current.canAccess.backup).toBe(false);
        });

        it('isViewer ist true', () => {
            mockUser.mockReturnValue(viewerUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.isViewer).toBe(true);
            expect(result.current.isEditor).toBe(false);
            expect(result.current.isAdmin).toBe(false);
        });
    });

    // ==================== Editor Role ====================

    describe('Editor Rolle', () => {
        const editorUser = {
            id: '2',
            email: 'editor@test.com',
            role: 'editor',
            is_superuser: false,
        };

        it('hat Lese- und Schreibrechte für Dokumente', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:read')).toBe(true);
            expect(result.current.hasPermission('documents:write')).toBe(true);
        });

        it('hat keine Lösch- und Verwaltungsrechte', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:delete')).toBe(false);
            expect(result.current.hasPermission('documents:manage')).toBe(false);
        });

        it('kann validation und training lesen/schreiben', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('validation:read')).toBe(true);
            expect(result.current.hasPermission('validation:write')).toBe(true);
            expect(result.current.hasPermission('training:read')).toBe(true);
            expect(result.current.hasPermission('training:write')).toBe(true);
        });

        it('hat keine manage-Rechte', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.validationManage).toBe(false);
            expect(result.current.canAccess.trainingManage).toBe(false);
            expect(result.current.canAccess.admin).toBe(false);
        });

        it('isEditor ist true', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.isEditor).toBe(true);
            expect(result.current.isViewer).toBe(false);
            expect(result.current.isAdmin).toBe(false);
        });
    });

    // ==================== Admin Role ====================

    describe('Admin Rolle', () => {
        const adminUser = {
            id: '3',
            email: 'admin@test.com',
            role: 'admin',
            is_superuser: false,
        };

        it('hat alle Dokumentrechte', () => {
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.hasPermission('documents:read')).toBe(true);
            expect(result.current.hasPermission('documents:write')).toBe(true);
            expect(result.current.hasPermission('documents:delete')).toBe(true);
            expect(result.current.hasPermission('documents:manage')).toBe(true);
        });

        it('hat alle manage-Rechte', () => {
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.validationManage).toBe(true);
            expect(result.current.canAccess.trainingManage).toBe(true);
            expect(result.current.canAccess.admin).toBe(true);
        });

        it('hat System- und Backup-Zugriff', () => {
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.system).toBe(true);
            expect(result.current.canAccess.backup).toBe(true);
        });

        it('isAdmin ist true', () => {
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.isAdmin).toBe(true);
            expect(result.current.isEditor).toBe(false);
            expect(result.current.isViewer).toBe(false);
        });
    });

    // ==================== Superuser ====================

    describe('Superuser', () => {
        const superuser = {
            id: '4',
            email: 'super@test.com',
            role: 'viewer', // Rolle ist egal bei Superuser
            is_superuser: true,
        };

        it('hat alle Berechtigungen unabhängig von der Rolle', () => {
            mockUser.mockReturnValue(superuser);

            const { result } = renderHook(() => usePermissions());

            // Selbst mit viewer-Rolle hat Superuser alle Rechte
            expect(result.current.hasPermission('documents:manage')).toBe(true);
            expect(result.current.hasPermission('users:manage')).toBe(true);
            expect(result.current.hasPermission('system:manage')).toBe(true);
            expect(result.current.hasPermission('backup:write')).toBe(true);
        });

        it('hasAnyPermission gibt true für beliebige Berechtigungen zurück', () => {
            mockUser.mockReturnValue(superuser);

            const { result } = renderHook(() => usePermissions());

            expect(
                result.current.hasAnyPermission('random:permission', 'nonexistent:perm')
            ).toBe(true);
        });

        it('hasAllPermissions gibt true für beliebige Berechtigungen zurück', () => {
            mockUser.mockReturnValue(superuser);

            const { result } = renderHook(() => usePermissions());

            expect(
                result.current.hasAllPermissions('documents:read', 'users:manage', 'system:manage')
            ).toBe(true);
        });

        it('hat alle canAccess Flags auf true', () => {
            mockUser.mockReturnValue(superuser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.canAccess.validation).toBe(true);
            expect(result.current.canAccess.validationManage).toBe(true);
            expect(result.current.canAccess.training).toBe(true);
            expect(result.current.canAccess.trainingManage).toBe(true);
            expect(result.current.canAccess.admin).toBe(true);
            expect(result.current.canAccess.users).toBe(true);
            expect(result.current.canAccess.system).toBe(true);
            expect(result.current.canAccess.backup).toBe(true);
        });

        it('isSuperuser und isAdmin sind true', () => {
            mockUser.mockReturnValue(superuser);

            const { result } = renderHook(() => usePermissions());

            expect(result.current.isSuperuser).toBe(true);
            expect(result.current.isAdmin).toBe(true);
        });
    });

    // ==================== hasAnyPermission ====================

    describe('hasAnyPermission', () => {
        const editorUser = {
            id: '2',
            email: 'editor@test.com',
            role: 'editor',
            is_superuser: false,
        };

        it('gibt true zurück wenn mindestens eine Berechtigung vorhanden', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            // Editor hat documents:write aber nicht documents:manage
            expect(
                result.current.hasAnyPermission('documents:write', 'documents:manage')
            ).toBe(true);
        });

        it('gibt false zurück wenn keine Berechtigung vorhanden', () => {
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            // Editor hat weder users:write noch system:manage
            expect(
                result.current.hasAnyPermission('users:write', 'system:manage')
            ).toBe(false);
        });
    });

    // ==================== hasAllPermissions ====================

    describe('hasAllPermissions', () => {
        const adminUser = {
            id: '3',
            email: 'admin@test.com',
            role: 'admin',
            is_superuser: false,
        };

        it('gibt true zurück wenn alle Berechtigungen vorhanden', () => {
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            expect(
                result.current.hasAllPermissions('documents:read', 'documents:write', 'documents:delete')
            ).toBe(true);
        });

        it('gibt false zurück wenn eine Berechtigung fehlt', () => {
            const editorUser = {
                id: '2',
                email: 'editor@test.com',
                role: 'editor',
                is_superuser: false,
            };
            mockUser.mockReturnValue(editorUser);

            const { result } = renderHook(() => usePermissions());

            // Editor hat documents:write aber nicht documents:delete
            expect(
                result.current.hasAllPermissions('documents:write', 'documents:delete')
            ).toBe(false);
        });
    });

    // ==================== Edge Cases ====================

    describe('Edge Cases', () => {
        it('behandelt User ohne Rolle als viewer', () => {
            const userWithoutRole = {
                id: '5',
                email: 'norole@test.com',
                // Keine role definiert
                is_superuser: false,
            };
            mockUser.mockReturnValue(userWithoutRole);

            const { result } = renderHook(() => usePermissions());

            // Sollte viewer-Berechtigungen haben
            expect(result.current.hasPermission('documents:read')).toBe(true);
            expect(result.current.hasPermission('documents:write')).toBe(false);
        });

        it('behandelt unbekannte Rolle als viewer', () => {
            const userWithUnknownRole = {
                id: '6',
                email: 'unknown@test.com',
                role: 'unknown_role',
                is_superuser: false,
            };
            mockUser.mockReturnValue(userWithUnknownRole);

            const { result } = renderHook(() => usePermissions());

            // Sollte auf viewer zurückfallen
            expect(result.current.hasPermission('documents:read')).toBe(true);
            expect(result.current.hasPermission('documents:write')).toBe(false);
        });

        it('prüft nicht existierende Berechtigung korrekt', () => {
            const adminUser = {
                id: '3',
                email: 'admin@test.com',
                role: 'admin',
                is_superuser: false,
            };
            mockUser.mockReturnValue(adminUser);

            const { result } = renderHook(() => usePermissions());

            // Admin hat diese Berechtigung nicht (sie existiert nicht)
            expect(result.current.hasPermission('nonexistent:permission')).toBe(false);
        });
    });
});
