/**
 * i18n Module - Internationalization for Ablage-System
 *
 * This module provides comprehensive internationalization support:
 * - German (de) as primary/source language
 * - English (en) as secondary language
 * - Namespace-based translation organization
 * - Locale-aware formatting utilities
 * - Type-safe translation hooks
 *
 * @example
 * ```tsx
 * // In App.tsx - initialize i18n
 * import './lib/i18n';
 *
 * // In components - use translations
 * import { useAppTranslation } from '@/lib/i18n';
 *
 * function MyComponent() {
 *   const { t, format, language, setLanguage } = useAppTranslation('documents');
 *
 *   return (
 *     <div>
 *       <h1>{t('title')}</h1>
 *       <p>{format.currency(1234.56)}</p>
 *       <button onClick={() => setLanguage('en')}>Switch to English</button>
 *     </div>
 *   );
 * }
 * ```
 *
 * @module lib/i18n
 */

// Main i18n configuration and instance
export { default } from './i18n';
export {
  changeLanguage,
  getCurrentLanguage,
  getCurrentLocale,
  getStoredLanguage,
  storeLanguage,
  isLanguageSupported,
  SUPPORTED_LANGUAGES,
  DEFAULT_LANGUAGE,
  FALLBACK_LANGUAGE,
  NAMESPACES,
  DEFAULT_NAMESPACE,
  LANGUAGE_NAMES,
  LANGUAGE_NATIVE_NAMES,
  LOCALE_CODES,
  type SupportedLanguage,
  type Namespace,
} from './i18n';

// Type-safe translation hooks
export {
  useAppTranslation,
  useTranslation,
  useDocumentsTranslation,
  useBankingTranslation,
  useEntitiesTranslation,
  useWorkflowTranslation,
  useErrorsTranslation,
  useAuthTranslation,
  useNavigationTranslation,
  useOcrTranslation,
  useAdminTranslation,
  useAlertsTranslation,
  type TranslationOptions,
  type UseTranslationReturn,
} from './useTranslation';

// Locale-aware formatting utilities
export {
  formatByLocale,
  getFormatters,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatFileSize,
  formatRelativeDate,
  type FormatOptions,
  type CurrencyFormatOptions,
  type DateFormatOptions,
  type NumberFormatOptions,
  type PercentFormatOptions,
} from './format';

// Re-export for backwards compatibility with old useLanguage hook
export { default as useLanguage } from './useLanguage';
