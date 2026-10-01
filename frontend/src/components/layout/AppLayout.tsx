"use client";

import React, { useState } from 'react';
import { usePathname } from 'next/navigation';
import { TopBar } from '@/components/UI/TopBar';
import { Sidebar } from '@/components/UI/Sidebar';
import { stationOptions } from '@/data/dashboard';
import { LanguageProvider } from '@/context/LanguageContext';
import { AuthProvider } from '@/context/AuthContext';
import { ForecastProvider } from '@/context/ForecastContext';

export function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [station, setStation] = useState(stationOptions[0]);
  const [target, setTarget] = useState('5000');

  const isLoginPage = pathname === '/login';

  return (
    <LanguageProvider>
      <AuthProvider>
        <ForecastProvider currentStation={station}>
          {isLoginPage ? (
            <div className="min-h-screen w-full bg-canvas">{children}</div>
          ) : (
            <div className="flex h-screen w-full flex-col overflow-hidden bg-canvas">
              <TopBar
                station={station}
                onStationChange={setStation}
                target={target}
                onTargetChange={setTarget}
              />
              <div className="flex min-h-0 flex-1">
                <Sidebar />
                <main className="flex min-w-0 flex-1 flex-col overflow-y-auto p-4">
                  {children}
                </main>
              </div>
            </div>
          )}
        </ForecastProvider>
      </AuthProvider>
    </LanguageProvider>
  );
}
