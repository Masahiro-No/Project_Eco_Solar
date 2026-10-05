"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  HomeIcon,
  MapPinIcon,
  LineChartIcon,
  LightbulbIcon,
  BellIcon,
  ClipboardCheckIcon,
  SatelliteIcon,
  BookOpenIcon,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useForecast } from '@/context/ForecastContext';
import { solarApi } from '@/services/api';

// adminOnly = private zone: shown to the admin role only (the API enforces the same rule)
const items = [
  { id: 'dashboard', key: 'nav_dashboard' as const, icon: HomeIcon, href: '/', adminOnly: false },
  { id: 'forecast', key: 'nav_forecast' as const, icon: LineChartIcon, href: '/forecast', adminOnly: false },
  { id: 'decision', key: 'nav_decision' as const, icon: LightbulbIcon, href: '/decision', adminOnly: false },
  { id: 'alerts', key: 'nav_alerts' as const, icon: BellIcon, href: '/alerts', adminOnly: false },
  { id: 'stations', key: 'nav_stations' as const, icon: MapPinIcon, href: '/stations', adminOnly: false },
  { id: 'labeling', key: 'nav_labeling' as const, icon: ClipboardCheckIcon, href: '/labeling', adminOnly: true },
  { id: 'frame-review', key: 'nav_frame_review' as const, icon: SatelliteIcon, href: '/frame-review', adminOnly: true },
  { id: 'help', key: 'nav_help' as const, icon: BookOpenIcon, href: '/help', adminOnly: false },
];

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslations('common');
  const { isAdmin } = useAuth();
  const { lastUpdated } = useForecast();
  const [alertCount, setAlertCount] = useState(0);

  // Real number of stations that need attention; refreshed with each new forecast
  useEffect(() => {
    let cancelled = false;
    solarApi.getAlerts().then((rows) => {
      if (!cancelled) setAlertCount(rows?.length ?? 0);
    });
    return () => {
      cancelled = true;
    };
  }, [lastUpdated]);

  return (
    <aside className="relative flex w-[64px] shrink-0 md:w-[230px] flex-col overflow-hidden border-r border-line bg-white shadow-sm">
      <nav aria-label="Main" className="flex flex-col gap-1 py-3">
        {items
          .filter((item) => !item.adminOnly || isAdmin)
          .map(({ id, key, icon: Icon, href }) => {
            const isActive = pathname === href || (href !== '/' && pathname?.startsWith(href));
            const badge = id === 'alerts' && alertCount > 0 ? alertCount : null;
            return (
              <Link
                key={id}
                href={href}
                aria-current={isActive ? 'page' : undefined}
                title={t(key)}
                className={`relative flex h-11 items-center justify-center gap-3.5 px-0 text-left md:justify-start md:px-5 text-[14px] font-medium transition-colors duration-150 ${
                  isActive ? 'bg-brand-soft text-brand font-semibold' : 'text-slate-700 hover:bg-canvas'
                }`}
              >
                {isActive && <span className="absolute left-0 top-0 h-full w-1 rounded-r bg-brand" />}
                <Icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.8} />
                <span className="hidden flex-1 whitespace-nowrap md:inline">{t(key)}</span>
                {badge !== null && (
                  <span
                    aria-label={t('alerts_badge', { n: badge })}
                    className="flex h-5 min-w-5 items-center justify-center rounded-full bg-bad px-1 text-[11px] font-bold text-white"
                  >
                    {badge}
                  </span>
                )}
              </Link>
            );
          })}
      </nav>
      <div className="mt-auto hidden md:block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/e43470af-70c2-412c-87b2-bb369e10d41a.jpg"
          alt=""
          loading="lazy"
          decoding="async"
          className="w-full object-cover mix-blend-multiply"
        />
        <p className="px-5 pb-4 pt-2 text-[13px] font-medium leading-5 text-muted">
          {t('clean_energy')}
          <br />
          {t('better_tomorrow')}
        </p>
      </div>
    </aside>
  );
}
