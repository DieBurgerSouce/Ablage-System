import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Import translations
import de from '@/locales/de.json';
import en from '@/locales/en.json';

// i18n Konfiguration für Ablage-System
// Primärsprache: Deutsch (de)
// Sekundärsprache: Englisch (en)

const resources = {
    de: { translation: de },
    en: { translation: en },
};

i18n
    .use(initReactI18next)
    .init({
        resources,
        lng: localStorage.getItem('language') || 'de', // Default: Deutsch
        fallbackLng: 'de',

        interpolation: {
            escapeValue: false, // React bereits XSS-sicher
        },

        // Namespace-Konfiguration
        defaultNS: 'translation',
        ns: ['translation'],

        // Debug-Modus (nur in Development)
        debug: import.meta.env.DEV,

        // Performance-Optimierungen
        load: 'languageOnly', // Nur 'de' statt 'de-DE'

        // React-spezifische Optionen
        react: {
            useSuspense: false, // Für bessere Kompatibilität
        },
    });

// Sprache wechseln und persistieren
export const changeLanguage = (lang: 'de' | 'en') => {
    localStorage.setItem('language', lang);
    i18n.changeLanguage(lang);
};

// Aktuelle Sprache abrufen
export const getCurrentLanguage = (): 'de' | 'en' => {
    return (i18n.language as 'de' | 'en') || 'de';
};

export default i18n;
