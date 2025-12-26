/**
 * User Model Types
 *
 * Typen fuer Benutzer, Authentifizierung und Autorisierung.
 */

// Types imported from '../api/common' as needed

// ==================== User Roles ====================

/**
 * User roles with permissions
 */
export type UserRole = 'admin' | 'editor' | 'viewer';

/**
 * Role permissions mapping
 */
export const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
    admin: [
        'user.create',
        'user.update',
        'user.delete',
        'document.create',
        'document.update',
        'document.delete',
        'settings.manage',
        'ocr.configure',
        'banking.manage',
    ],
    editor: [
        'document.create',
        'document.update',
        'document.delete',
        'ocr.process',
        'banking.view',
    ],
    viewer: [
        'document.view',
        'ocr.view',
        'banking.view',
    ],
};

// ==================== User ====================

/**
 * User entity
 */
export interface User {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_superuser: boolean;
    is_active: boolean;
    role: UserRole;
}

/**
 * User profile with additional details
 */
export interface UserProfile extends User {
    avatar_url?: string;
    phone?: string;
    language?: 'de' | 'en';
    timezone?: string;
    created_at?: string;
    last_login?: string;
}

/**
 * User for admin management
 */
export interface UserAdmin extends User {
    created_at: string;
    updated_at: string;
    last_login?: string;
    login_count: number;
}

// ==================== Authentication ====================

/**
 * Login credentials
 */
export interface LoginCredentials {
    email: string;
    password: string;
    remember_me?: boolean;
}

/**
 * Login response from backend
 */
export interface LoginResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    session_warning?: string | null;
}

/**
 * Auth response for frontend
 */
export interface AuthResponse {
    user: User;
    token: string;
    refreshToken: string;
}

/**
 * Token refresh request
 */
export interface RefreshTokenRequest {
    refresh_token: string;
}

/**
 * Password reset request
 */
export interface PasswordResetRequest {
    email: string;
}

/**
 * Password reset confirmation
 */
export interface PasswordResetConfirm {
    token: string;
    new_password: string;
}

/**
 * Password change request
 */
export interface PasswordChangeRequest {
    current_password: string;
    new_password: string;
}

// ==================== User Management ====================

/**
 * User create request
 */
export interface UserCreateRequest {
    email: string;
    username: string;
    password: string;
    full_name?: string;
    role?: UserRole;
    is_active?: boolean;
}

/**
 * User update request
 */
export interface UserUpdateRequest {
    email?: string;
    username?: string;
    full_name?: string;
    role?: UserRole;
    is_active?: boolean;
}

/**
 * User response from backend
 */
export interface UserResponse {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_superuser: boolean;
    is_active: boolean;
}

// ==================== Session ====================

/**
 * Active session information
 */
export interface Session {
    id: string;
    user_id: string;
    device?: string;
    ip_address?: string;
    user_agent?: string;
    created_at: string;
    last_activity: string;
    is_current: boolean;
}

// ==================== Permissions ====================

/**
 * Permission check result
 */
export interface PermissionCheck {
    allowed: boolean;
    reason?: string;
}

/**
 * Check if user has permission
 */
export function hasPermission(user: User, permission: string): boolean {
    const permissions = ROLE_PERMISSIONS[user.role] || [];
    return permissions.includes(permission) || user.is_superuser;
}

/**
 * Check if user has any of the required roles
 */
export function hasRole(user: User, roles: UserRole[]): boolean {
    return roles.includes(user.role) || user.is_superuser;
}
