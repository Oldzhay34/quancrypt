import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { en } from './en';
import { tr } from './tr';
import type { MessageKey } from './tr';

export type Language = 'tr' | 'en';
const STORAGE_KEY = 'quancrypt.lang';
const DICTIONARIES: Record<Language, Record<MessageKey, string>> = { tr, en };

function initialLanguage(): Language {
    try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        if (saved === 'tr' || saved === 'en') return saved;
    } catch {
        // Storage blocked: the default applies.
    }
    return 'tr';
}

interface I18nValue {
    language: Language;
    setLanguage: (language: Language) => void;
    t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
    const [language, setLanguageState] = useState<Language>(initialLanguage);

    const setLanguage = useCallback((next: Language) => {
        setLanguageState(next);
        try {
            window.localStorage.setItem(STORAGE_KEY, next);
        } catch {
            // The choice then lasts for this page only.
        }
    }, []);

    useEffect(() => {
        document.documentElement.lang = language;
    }, [language]);

    const value = useMemo<I18nValue>(
        () => ({
            language,
            setLanguage,
            t: (key, params) => {
                let text = DICTIONARIES[language][key];
                for (const [name, replacement] of Object.entries(params ?? {})) {
                    text = text.replaceAll(`{${name}}`, String(replacement));
                }
                return text;
            },
        }),
        [language, setLanguage],
    );
    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
    const value = useContext(I18nContext);
    if (!value) throw new Error('useI18n must be used inside I18nProvider');
    return value;
}
