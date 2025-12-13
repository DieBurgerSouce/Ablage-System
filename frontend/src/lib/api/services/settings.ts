/**
 * Settings API Service.
 *
 * Provides API calls for:
 * - User settings (display, OCR, notifications, privacy)
 * - Company settings (admin only)
 * - Tag management (admin only)
 */

import { apiClient } from '../client';
import type { Tag, TagCreate, TagUpdate } from '@/features/upload/types';

// ==================== Type Definitions ====================

export interface DisplaySettings {
    display_mode: 'light' | 'dark' | 'whitescreen' | 'blackscreen';
    language: 'de' | 'en';
    items_per_page: number;
    show_previews: boolean;
    compact_view: boolean;
}

export interface OCRSettings {
    default_backend: 'auto' | 'deepseek' | 'got_ocr' | 'surya';
    default_language: string;
    auto_start_ocr: boolean;
    default_priority: number;
}

export interface NotificationSettings {
    email_on_ocr_complete: boolean;
    email_on_ocr_failed: boolean;
    email_on_share: boolean;
    email_digest: 'none' | 'daily' | 'weekly';
}

export interface PrivacySettings {
    share_analytics: boolean;
    show_profile_to_others: boolean;
    allow_search_indexing: boolean;
}

export interface UserSettings {
    display: DisplaySettings;
    ocr: OCRSettings;
    notifications: NotificationSettings;
    privacy: PrivacySettings;
    last_updated: string;
}

export interface CompanySettings {
    id: string;
    company_name: string;
    alternative_names: string[];
    street: string | null;
    postal_code: string | null;
    city: string | null;
    country: string;
    vat_id: string | null;
    tax_number: string | null;
    iban: string | null;
    bic: string | null;
    email: string | null;
    phone: string | null;
    website: string | null;
    commercial_register: string | null;
    court: string | null;
    created_at: string;
    updated_at: string;
    updated_by_id: string | null;
}

export interface CompanySettingsUpdate {
    company_name: string;
    alternative_names?: string[];
    street?: string | null;
    postal_code?: string | null;
    city?: string | null;
    country?: string;
    vat_id?: string | null;
    tax_number?: string | null;
    iban?: string | null;
    bic?: string | null;
    email?: string | null;
    phone?: string | null;
    website?: string | null;
    commercial_register?: string | null;
    court?: string | null;
}

export interface CompanySettingsEmpty {
    message: string;
    configured: boolean;
}

// ==================== Settings Service ====================

export const settingsService = {
    // ========== User Settings ==========

    /**
     * Ruft alle Benutzereinstellungen ab.
     */
    getAllSettings: async (): Promise<UserSettings> => {
        const response = await apiClient.get<UserSettings>('/settings/');
        return response.data;
    },

    /**
     * Aktualisiert mehrere Einstellungsbereiche gleichzeitig.
     */
    updateSettings: async (settings: Partial<{
        display: Partial<DisplaySettings>;
        ocr: Partial<OCRSettings>;
        notifications: Partial<NotificationSettings>;
        privacy: Partial<PrivacySettings>;
    }>): Promise<UserSettings> => {
        const response = await apiClient.put<UserSettings>('/settings/', settings);
        return response.data;
    },

    /**
     * Setzt alle Einstellungen auf Standardwerte zurueck.
     */
    resetSettings: async (): Promise<{ message: string; reset_at: string }> => {
        const response = await apiClient.post<{ message: string; reset_at: string }>('/settings/reset');
        return response.data;
    },

    // ========== Display Settings ==========

    /**
     * Ruft nur Anzeigeeinstellungen ab.
     */
    getDisplaySettings: async (): Promise<DisplaySettings> => {
        const response = await apiClient.get<DisplaySettings>('/settings/display');
        return response.data;
    },

    /**
     * Aktualisiert Anzeigeeinstellungen.
     */
    updateDisplaySettings: async (settings: DisplaySettings): Promise<DisplaySettings> => {
        const response = await apiClient.put<DisplaySettings>('/settings/display', settings);
        return response.data;
    },

    // ========== OCR Settings ==========

    /**
     * Ruft nur OCR-Einstellungen ab.
     */
    getOCRSettings: async (): Promise<OCRSettings> => {
        const response = await apiClient.get<OCRSettings>('/settings/ocr');
        return response.data;
    },

    /**
     * Aktualisiert OCR-Einstellungen.
     */
    updateOCRSettings: async (settings: OCRSettings): Promise<OCRSettings> => {
        const response = await apiClient.put<OCRSettings>('/settings/ocr', settings);
        return response.data;
    },

    // ========== Notification Settings ==========

    /**
     * Ruft nur Benachrichtigungseinstellungen ab.
     */
    getNotificationSettings: async (): Promise<NotificationSettings> => {
        const response = await apiClient.get<NotificationSettings>('/settings/notifications');
        return response.data;
    },

    /**
     * Aktualisiert Benachrichtigungseinstellungen.
     */
    updateNotificationSettings: async (settings: NotificationSettings): Promise<NotificationSettings> => {
        const response = await apiClient.put<NotificationSettings>('/settings/notifications', settings);
        return response.data;
    },

    // ========== Privacy Settings ==========

    /**
     * Ruft nur Datenschutzeinstellungen ab.
     */
    getPrivacySettings: async (): Promise<PrivacySettings> => {
        const response = await apiClient.get<PrivacySettings>('/settings/privacy');
        return response.data;
    },

    /**
     * Aktualisiert Datenschutzeinstellungen.
     */
    updatePrivacySettings: async (settings: PrivacySettings): Promise<PrivacySettings> => {
        const response = await apiClient.put<PrivacySettings>('/settings/privacy', settings);
        return response.data;
    },

    // ========== Company Settings (Admin Only) ==========

    /**
     * Ruft Firmendaten ab (nur Admin).
     */
    getCompanySettings: async (): Promise<CompanySettings | CompanySettingsEmpty> => {
        const response = await apiClient.get<CompanySettings | CompanySettingsEmpty>('/admin/company');
        return response.data;
    },

    /**
     * Aktualisiert oder erstellt Firmendaten (nur Admin).
     */
    updateCompanySettings: async (settings: CompanySettingsUpdate): Promise<CompanySettings> => {
        const response = await apiClient.put<CompanySettings>('/admin/company', settings);
        return response.data;
    },

    /**
     * Loescht Firmendaten (nur Admin).
     */
    deleteCompanySettings: async (): Promise<void> => {
        await apiClient.delete('/admin/company');
    },

    /**
     * Prueft ob Firmendaten konfiguriert sind.
     */
    isCompanyConfigured: (settings: CompanySettings | CompanySettingsEmpty): settings is CompanySettings => {
        return 'id' in settings && !('configured' in settings && settings.configured === false);
    },

    // ========== Tag Settings (Admin Only) ==========

    /**
     * Ruft alle Tags ab (nur Admin).
     */
    getTags: async (options?: { activeOnly?: boolean; systemOnly?: boolean }): Promise<Tag[]> => {
        const params = new URLSearchParams();
        if (options?.activeOnly) params.append('active_only', 'true');
        if (options?.systemOnly) params.append('system_only', 'true');

        const url = params.toString() ? `/admin/tags?${params.toString()}` : '/admin/tags';
        const response = await apiClient.get<Tag[]>(url);
        return response.data;
    },

    /**
     * Ruft ein einzelnes Tag ab (nur Admin).
     */
    getTag: async (id: string): Promise<Tag> => {
        const response = await apiClient.get<Tag>(`/admin/tags/${id}`);
        return response.data;
    },

    /**
     * Erstellt ein neues Tag (nur Admin).
     */
    createTag: async (tag: TagCreate): Promise<Tag> => {
        const response = await apiClient.post<Tag>('/admin/tags', tag);
        return response.data;
    },

    /**
     * Aktualisiert ein Tag (nur Admin).
     */
    updateTag: async (id: string, tag: TagUpdate): Promise<Tag> => {
        const response = await apiClient.put<Tag>(`/admin/tags/${id}`, tag);
        return response.data;
    },

    /**
     * Loescht ein Tag (nur Admin, System-Tags geschuetzt).
     */
    deleteTag: async (id: string): Promise<void> => {
        await apiClient.delete(`/admin/tags/${id}`);
    },
};
