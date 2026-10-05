"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type Theme = 'light' | 'dark';

/** Where the choice is kept. The same key is read by the inline script in app/layout.tsx before first paint. */
export const THEME_STORAGE_KEY = 'solar_theme';

type ThemeContextType = { theme: Theme; setTheme: (theme: Theme) => void; toggleTheme: () => void };

const ThemeContext = createContext<ThemeContextType>({ theme: 'light', setTheme: () => {}, toggleTheme: () => {} });

/**
 * Light is the default look; dark is chosen with the switch in the top bar and remembered in this browser.
 * The look itself lives in app/globals.css (data-theme="dark" on <html>).
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('light');

  // the inline script has already applied the saved choice to <html>; read it back so the switch shows it
  useEffect(() => {
    setThemeState(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    if (next === 'dark') document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // storage blocked: the choice still holds for this page
    }
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme: () => setTheme(theme === 'dark' ? 'light' : 'dark') }),
    [theme, setTheme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
