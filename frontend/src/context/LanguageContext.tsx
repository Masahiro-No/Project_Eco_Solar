"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import thMessages from '@/messages/th.json';
import enMessages from '@/messages/en.json';

type Locale = 'th' | 'en';

type LanguageContextType = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  toggleLanguage: () => void;
};

const messagesMap = {
  th: thMessages,
  en: enMessages,
};

const LanguageContext = createContext<LanguageContextType>({
  locale: 'th',
  setLocale: () => {},
  toggleLanguage: () => {},
});

const COOKIE_NAME = 'solar_locale';

export function LanguageProvider({
  children,
  initialLocale = 'th',
}: {
  children: React.ReactNode;
  /** Read from the cookie on the server so the first paint is already in the right language */
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  // Keep <html lang> in sync for screen readers / hyphenation / font selection
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    document.cookie = `${COOKIE_NAME}=${l}; path=/; max-age=31536000; samesite=lax`;
    try {
      localStorage.setItem('solar_locale', l);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const toggleLanguage = useCallback(() => {
    setLocale(locale === 'th' ? 'en' : 'th');
  }, [locale, setLocale]);

  const value = useMemo(() => ({ locale, setLocale, toggleLanguage }), [locale, setLocale, toggleLanguage]);

  return (
    <LanguageContext.Provider value={value}>
      <NextIntlClientProvider locale={locale} messages={messagesMap[locale]}>
        {children}
      </NextIntlClientProvider>
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
