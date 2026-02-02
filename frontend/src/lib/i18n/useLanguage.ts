/**
 * Hook for language switching in Ablage-System (Legacy Compatibility)
 *
 * This hook provides backwards compatibility with the old useLanguage pattern.
 * For new code, use `useAppTranslation` from '@/lib/i18n' instead.
 *
 * @deprecated Use `useAppTranslation` from '@/lib/i18n' for new code
 *
 * @example
 * ```tsx
 * // Legacy usage (still supported)
 * const { language, setLanguage, t } = useLanguage();
 *
 * // New recommended usage
 * const { language, setLanguage, t, format } = useAppTranslation();
 * ```
 */

import { useTranslation } from 'react-i18next';
import { changeLanguage, getCurrentLanguage, type SupportedLanguage } from './i18n';

export function useLanguage() {
    const { t, i18n } = useTranslation();

    const language = getCurrentLanguage();

    const setLanguage = async (lang: 'de' | 'en') => {
        await changeLanguage(lang as SupportedLanguage);
    };

    const toggleLanguage = async () => {
        const newLang = language === 'de' ? 'en' : 'de';
        await setLanguage(newLang);
    };

    return {
        language,
        setLanguage,
        toggleLanguage,
        t,
        i18n,
    };
}

export default useLanguage;
