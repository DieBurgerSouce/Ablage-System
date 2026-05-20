/**
 * i18n Configuration (Legacy Compatibility)
 *
 * This file provides backwards compatibility with the old i18n setup.
 * For new code, import from '@/lib/i18n' instead.
 *
 * @deprecated Use `import { ... } from '@/lib/i18n'` instead
 */

// Re-export from new i18n module
import i18n, {
    changeLanguage as newChangeLanguage,
    getCurrentLanguage as newGetCurrentLanguage,
    type SupportedLanguage,
} from './i18n';

// Legacy exports for backwards compatibility
export const changeLanguage = (lang: 'de' | 'en') => {
    return newChangeLanguage(lang as SupportedLanguage);
};

export const getCurrentLanguage = (): 'de' | 'en' => {
    return newGetCurrentLanguage() as 'de' | 'en';
};

export default i18n;
