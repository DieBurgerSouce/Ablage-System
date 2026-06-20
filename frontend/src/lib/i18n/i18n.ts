/**
 * i18n Configuration for Ablage-System
 *
 * Multi-language support with German as primary language.
 * Uses react-i18next with namespace-based organization.
 *
 * Structure:
 * - German (de): Source of truth, all content must exist in German first
 * - English (en): Secondary language, fallback to German if missing
 *
 * @module lib/i18n
 */

import i18n from 'i18next';
import { logger } from '@/lib/logger';
import { initReactI18next } from 'react-i18next';

// Import translation namespaces - German (source of truth)
import deCommon from './locales/de/common.json';
import deDocuments from './locales/de/documents.json';
import deBanking from './locales/de/banking.json';
import deEntities from './locales/de/entities.json';
import deWorkflow from './locales/de/workflow.json';
import deErrors from './locales/de/errors.json';
import deAuth from './locales/de/auth.json';
import deNavigation from './locales/de/navigation.json';
import deOcr from './locales/de/ocr.json';
import deAdmin from './locales/de/admin.json';
import deAlerts from './locales/de/alerts.json';

// Import translation namespaces - English
import enCommon from './locales/en/common.json';
import enDocuments from './locales/en/documents.json';
import enBanking from './locales/en/banking.json';
import enEntities from './locales/en/entities.json';
import enWorkflow from './locales/en/workflow.json';
import enErrors from './locales/en/errors.json';
import enAuth from './locales/en/auth.json';
import enNavigation from './locales/en/navigation.json';
import enOcr from './locales/en/ocr.json';
import enAdmin from './locales/en/admin.json';
import enAlerts from './locales/en/alerts.json';

/** Supported languages */
export const SUPPORTED_LANGUAGES = ['de', 'en'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

/** Default language (German) */
export const DEFAULT_LANGUAGE: SupportedLanguage = 'de';

/** Fallback language (German - source of truth) */
export const FALLBACK_LANGUAGE: SupportedLanguage = 'de';

/** Available namespaces */
export const NAMESPACES = [
  'common',
  'documents',
  'banking',
  'entities',
  'workflow',
  'errors',
  'auth',
  'navigation',
  'ocr',
  'admin',
  'alerts',
] as const;

export type Namespace = (typeof NAMESPACES)[number];

/** Default namespace */
export const DEFAULT_NAMESPACE: Namespace = 'common';

/** Language display names */
export const LANGUAGE_NAMES: Record<SupportedLanguage, string> = {
  de: 'Deutsch',
  en: 'English',
};

/** Language native names */
export const LANGUAGE_NATIVE_NAMES: Record<SupportedLanguage, string> = {
  de: 'Deutsch',
  en: 'English',
};

/** Locale codes for Intl APIs */
export const LOCALE_CODES: Record<SupportedLanguage, string> = {
  de: 'de-DE',
  en: 'en-US',
};

// Bundle all translations
const resources = {
  de: {
    common: deCommon,
    documents: deDocuments,
    banking: deBanking,
    entities: deEntities,
    workflow: deWorkflow,
    errors: deErrors,
    auth: deAuth,
    navigation: deNavigation,
    ocr: deOcr,
    admin: deAdmin,
    alerts: deAlerts,
  },
  en: {
    common: enCommon,
    documents: enDocuments,
    banking: enBanking,
    entities: enEntities,
    workflow: enWorkflow,
    errors: enErrors,
    auth: enAuth,
    navigation: enNavigation,
    ocr: enOcr,
    admin: enAdmin,
    alerts: enAlerts,
  },
};

/**
 * Get the stored language preference from localStorage
 */
export function getStoredLanguage(): SupportedLanguage {
  if (typeof window === 'undefined') {
    return DEFAULT_LANGUAGE;
  }

  const stored = localStorage.getItem('language');
  if (stored && SUPPORTED_LANGUAGES.includes(stored as SupportedLanguage)) {
    return stored as SupportedLanguage;
  }

  // Try browser language
  const browserLang = navigator.language.split('-')[0];
  if (SUPPORTED_LANGUAGES.includes(browserLang as SupportedLanguage)) {
    return browserLang as SupportedLanguage;
  }

  return DEFAULT_LANGUAGE;
}

/**
 * Store language preference
 */
export function storeLanguage(lang: SupportedLanguage): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem('language', lang);
  }
}

// Initialize i18n
i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: getStoredLanguage(),
    fallbackLng: FALLBACK_LANGUAGE,

    // Namespace configuration
    defaultNS: DEFAULT_NAMESPACE,
    ns: [...NAMESPACES],

    // Interpolation settings
    interpolation: {
      escapeValue: false, // React handles XSS
      formatSeparator: ',',
    },

    // Key handling
    keySeparator: '.', // Allow nested keys: "common.button.save"
    nsSeparator: ':', // Allow namespace prefix: "errors:notFound"

    // Debug mode (development only)
    debug: import.meta.env.DEV && import.meta.env.VITE_I18N_DEBUG === 'true',

    // Performance optimizations
    load: 'languageOnly', // Only 'de' not 'de-DE'
    returnNull: false,
    returnEmptyString: false,

    // React-specific options
    react: {
      useSuspense: false, // For better compatibility
      bindI18n: 'languageChanged',
      bindI18nStore: '',
      transEmptyNodeValue: '',
      transSupportBasicHtmlNodes: true,
      transKeepBasicHtmlNodesFor: ['br', 'strong', 'i', 'em', 'b', 'u'],
    },

    // Missing key handling
    saveMissing: import.meta.env.DEV,
    missingKeyHandler: (lng, ns, key, fallbackValue) => {
      if (import.meta.env.DEV) {
        logger.warn(`[i18n] Missing translation: ${lng}/${ns}/${key} (fallback: ${fallbackValue})`);
      }
    },
  });

/**
 * Change the current language
 */
export async function changeLanguage(lang: SupportedLanguage): Promise<void> {
  storeLanguage(lang);
  await i18n.changeLanguage(lang);
}

/**
 * Get current language
 */
export function getCurrentLanguage(): SupportedLanguage {
  return (i18n.language as SupportedLanguage) || DEFAULT_LANGUAGE;
}

/**
 * Get locale code for current language (for Intl APIs)
 */
export function getCurrentLocale(): string {
  return LOCALE_CODES[getCurrentLanguage()];
}

/**
 * Check if a language is supported
 */
export function isLanguageSupported(lang: string): lang is SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(lang as SupportedLanguage);
}

export default i18n;
