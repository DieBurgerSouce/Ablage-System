/**
 * Type-safe translation hook for Ablage-System
 *
 * Provides type-safe access to translations with:
 * - Namespace-aware translation function
 * - Plural support
 * - Interpolation with type checking
 * - Integration with formatting utilities
 *
 * @module lib/i18n/useTranslation
 */

import { useTranslation as useI18nextTranslation, type UseTranslationOptions } from 'react-i18next';
import { useCallback, useMemo } from 'react';
import { type SupportedLanguage, type Namespace, DEFAULT_NAMESPACE, changeLanguage, getCurrentLanguage, getCurrentLocale, LANGUAGE_NAMES, SUPPORTED_LANGUAGES } from './i18n';
import { formatByLocale } from './format';

// Re-export types
export type { SupportedLanguage, Namespace };

/**
 * Translation options for interpolation
 */
export interface TranslationOptions {
  /** Interpolation values */
  [key: string]: string | number | boolean | undefined;
  /** Count for pluralization */
  count?: number;
  /** Context for contextual translations */
  context?: string;
  /** Default value if key not found */
  defaultValue?: string;
}

/**
 * Extended translation hook return type
 */
export interface UseTranslationReturn {
  /** Translation function - t(key, options?) */
  t: (key: string, options?: TranslationOptions) => string;
  /** Translation function with explicit namespace */
  tn: (namespace: Namespace, key: string, options?: TranslationOptions) => string;
  /** Current language */
  language: SupportedLanguage;
  /** Current locale code (e.g., 'de-DE') */
  locale: string;
  /** Set language */
  setLanguage: (lang: SupportedLanguage) => Promise<void>;
  /** Toggle between de/en */
  toggleLanguage: () => Promise<void>;
  /** Check if current language */
  isLanguage: (lang: SupportedLanguage) => boolean;
  /** Available languages with display names */
  languages: Array<{ code: SupportedLanguage; name: string }>;
  /** i18n ready state */
  ready: boolean;
  /** Format utilities (locale-aware) */
  format: ReturnType<typeof formatByLocale>;
  /** Check if translation key exists */
  exists: (key: string, namespace?: Namespace) => boolean;
}

/**
 * Type-safe translation hook
 *
 * @param namespace - Primary namespace (default: 'common')
 * @param options - Additional options
 *
 * @example
 * ```tsx
 * // Basic usage with default namespace
 * const { t, language, setLanguage } = useAppTranslation();
 * <span>{t('button.save')}</span>
 *
 * // With specific namespace
 * const { t } = useAppTranslation('documents');
 * <span>{t('upload.title')}</span>
 *
 * // With interpolation
 * <span>{t('greeting', { name: 'Max' })}</span>
 *
 * // With pluralization
 * <span>{t('items', { count: 5 })}</span>
 *
 * // With explicit namespace
 * const { tn } = useAppTranslation();
 * <span>{tn('errors', 'notFound')}</span>
 *
 * // With formatting
 * const { format } = useAppTranslation();
 * <span>{format.currency(1234.56)}</span>
 * ```
 */
export function useAppTranslation(
  namespace: Namespace = DEFAULT_NAMESPACE,
  options?: UseTranslationOptions<Namespace>
): UseTranslationReturn {
  const { t, i18n, ready } = useI18nextTranslation(namespace, options);

  const language = getCurrentLanguage();
  const locale = getCurrentLocale();

  // Translation function with explicit namespace
  const tn = useCallback(
    (ns: Namespace, key: string, opts?: TranslationOptions) => {
      return t(`${ns}:${key}`, opts) as string;
    },
    [t]
  );

  // Language setter
  const setLanguage = useCallback(async (lang: SupportedLanguage) => {
    await changeLanguage(lang);
  }, []);

  // Toggle between languages
  const toggleLanguage = useCallback(async () => {
    const newLang = language === 'de' ? 'en' : 'de';
    await changeLanguage(newLang);
  }, [language]);

  // Check current language
  const isLanguage = useCallback(
    (lang: SupportedLanguage) => language === lang,
    [language]
  );

  // Check if key exists
  const exists = useCallback(
    (key: string, ns: Namespace = namespace) => {
      return i18n.exists(`${ns}:${key}`);
    },
    [i18n, namespace]
  );

  // Available languages
  const languages = useMemo(
    () =>
      SUPPORTED_LANGUAGES.map((code) => ({
        code,
        name: LANGUAGE_NAMES[code],
      })),
    []
  );

  // Format utilities
  const format = useMemo(() => formatByLocale(language), [language]);

  return {
    t: t as (key: string, options?: TranslationOptions) => string,
    tn,
    language,
    locale,
    setLanguage,
    toggleLanguage,
    isLanguage,
    languages,
    ready,
    format,
    exists,
  };
}

/**
 * Hook for documents namespace
 */
export function useDocumentsTranslation() {
  return useAppTranslation('documents');
}

/**
 * Hook for banking namespace
 */
export function useBankingTranslation() {
  return useAppTranslation('banking');
}

/**
 * Hook for entities namespace
 */
export function useEntitiesTranslation() {
  return useAppTranslation('entities');
}

/**
 * Hook for workflow namespace
 */
export function useWorkflowTranslation() {
  return useAppTranslation('workflow');
}

/**
 * Hook for errors namespace
 */
export function useErrorsTranslation() {
  return useAppTranslation('errors');
}

/**
 * Hook for auth namespace
 */
export function useAuthTranslation() {
  return useAppTranslation('auth');
}

/**
 * Hook for navigation namespace
 */
export function useNavigationTranslation() {
  return useAppTranslation('navigation');
}

/**
 * Hook for OCR namespace
 */
export function useOcrTranslation() {
  return useAppTranslation('ocr');
}

/**
 * Hook for admin namespace
 */
export function useAdminTranslation() {
  return useAppTranslation('admin');
}

/**
 * Hook for alerts namespace
 */
export function useAlertsTranslation() {
  return useAppTranslation('alerts');
}

// Re-export for backwards compatibility
export { useAppTranslation as useTranslation };

export default useAppTranslation;
