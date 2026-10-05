"use client";

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { TopBar } from '@/components/UI/TopBar';
import { Sidebar } from '@/components/UI/Sidebar';
import { LanguageProvider } from '@/context/LanguageContext';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { ForecastProvider } from '@/context/ForecastContext';
import { ThemeProvider } from '@/context/ThemeContext';

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isLoggedIn, isLoading } = useAuth();

  const isLoginPage = pathname === '/login';

  // Route guard: unauthenticated users are sent to /login
  useEffect(() => {
    if (!isLoading && !isLoggedIn && !isLoginPage) {
      router.replace('/login');
    }
  }, [isLoading, isLoggedIn, isLoginPage, router]);

  if (isLoginPage) {
    return <div className="min-h-screen w-full bg-canvas">{children}</div>;
  }

  if (isLoading || !isLoggedIn) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen w-full items-center justify-center bg-canvas text-sm text-muted"
      >
        Loading…
      </div>
    );
  }

  return (
    <ForecastProvider>
      <div className="flex h-screen w-full flex-col overflow-hidden bg-canvas">
        <TopBar />
        <div className="flex min-h-0 flex-1">
          <Sidebar />
          <main className="flex min-w-0 flex-1 flex-col overflow-y-auto p-4">{children}</main>
        </div>
      </div>
    </ForecastProvider>
  );
}

export function AppLayout({
  children,
  initialLocale = 'th',
}: {
  children: React.ReactNode;
  initialLocale?: 'th' | 'en';
}) {
  return (
    <ThemeProvider>
      <LanguageProvider initialLocale={initialLocale}>
        <AuthProvider>
          <Shell>{children}</Shell>
        </AuthProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}
