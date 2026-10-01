"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
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

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('th');

  useEffect(() => {
    const saved = localStorage.getItem('solar_locale') as Locale | null;
    if (saved && (saved === 'th' || saved === 'en')) {
      setLocaleState(saved);
    }
  }, []);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    localStorage.setItem('solar_locale', l);
  };

  const toggleLanguage = () => {
    const nextLocale = locale === 'th' ? 'en' : 'th';
    setLocale(nextLocale);
  };

  return (
    <LanguageContext.Provider value={{ locale, setLocale, toggleLanguage }}>
      <NextIntlClientProvider locale={locale} messages={messagesMap[locale]}>
        {children}
      </NextIntlClientProvider>
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}
