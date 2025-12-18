import { useTranslation } from 'react-i18next';
import { changeLanguage, getCurrentLanguage } from './config';

/**
 * Hook für Sprachwechsel im Ablage-System
 *
 * Verwendung:
 * ```tsx
 * const { language, setLanguage, t } = useLanguage();
 *
 * // Sprache wechseln
 * setLanguage('en');
 *
 * // Übersetzung verwenden
 * <span>{t('common.save')}</span>
 * ```
 */
export function useLanguage() {
    const { t, i18n } = useTranslation();

    const language = getCurrentLanguage();

    const setLanguage = (lang: 'de' | 'en') => {
        changeLanguage(lang);
    };

    const toggleLanguage = () => {
        const newLang = language === 'de' ? 'en' : 'de';
        setLanguage(newLang);
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
