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
  DatabaseIcon,
  RepeatIcon,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useForecast } from '@/context/ForecastContext';
import { solarApi } from '@/services/api';

// Pages grouped by what the user comes to do.
// adminOnly = private zone: shown to the admin role only (the API enforces the same rule)
const groups = [
  {
    id: 'monitor',
    key: 'nav_group_monitor' as const,
    adminOnly: false,
    items: [
      { id: 'dashboard', key: 'nav_dashboard' as const, icon: HomeIcon, href: '/' },
      { id: 'forecast', key: 'nav_forecast' as const, icon: LineChartIcon, href: '/forecast' },
      { id: 'decision', key: 'nav_decision' as const, icon: LightbulbIcon, href: '/decision' },
      { id: 'alerts', key: 'nav_alerts' as const, icon: BellIcon, href: '/alerts' },
    ],
  },
  {
    id: 'data',
    key: 'nav_group_data' as const,
    adminOnly: false,
    items: [
      { id: 'stations', key: 'nav_stations' as const, icon: MapPinIcon, href: '/stations' },
      { id: 'inputs', key: 'nav_inputs' as const, icon: DatabaseIcon, href: '/inputs' },
    ],
  },
  {
    id: 'models',
    key: 'nav_group_models' as const,
    adminOnly: true,
    items: [
      { id: 'labeling', key: 'nav_labeling' as const, icon: ClipboardCheckIcon, href: '/labeling' },
      { id: 'frame-review', key: 'nav_frame_review' as const, icon: SatelliteIcon, href: '/frame-review' },
      { id: 'retrain', key: 'nav_retrain' as const, icon: RepeatIcon, href: '/retrain' },
    ],
  },
  {
    id: 'help',
    key: 'nav_group_help' as const,
    adminOnly: false,
    items: [{ id: 'help', key: 'nav_help' as const, icon: BookOpenIcon, href: '/help' }],
  },
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
      {/* the menu scrolls by itself when the window is too short for all groups */}
      <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col overflow-y-auto pb-3 pt-1">
        {groups
          .filter((group) => !group.adminOnly || isAdmin)
          .map((group, index) => (
            <div
              key={group.id}
              role="group"
              aria-labelledby={`nav-group-${group.id}`}
              // icon-only width: no room for the group name, a line separates the groups instead
              className={`flex flex-col gap-1 ${index > 0 ? 'mt-2 border-t border-line pt-2 md:mt-0 md:border-t-0 md:pt-0' : 'pt-2 md:pt-0'}`}
            >
              <p
                id={`nav-group-${group.id}`}
                className="hidden items-baseline justify-between gap-2 px-5 pb-0.5 pt-3 text-[11.5px] font-semibold text-muted md:flex"
              >
                <span>{t(group.key)}</span>{' '}
                {group.adminOnly && <span className="font-normal">{t('nav_admin_only')}</span>}
              </p>
              {group.items.map(({ id, key, icon: Icon, href }) => {
                const isActive = pathname === href || (href !== '/' && pathname?.startsWith(href));
                const badge = id === 'alerts' && alertCount > 0 ? alertCount : null;
                return (
                  <Link
                    key={id}
                    href={href}
                    aria-current={isActive ? 'page' : undefined}
                    title={t(key)}
                    className={`relative flex h-10 shrink-0 items-center justify-center gap-3.5 px-0 text-left md:justify-start md:px-5 text-[14px] font-medium transition-colors duration-150 ${
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
            </div>
          ))}
      </nav>
      {/* decoration: shown only when the window is tall enough to keep the whole menu in view */}
      <div className="hidden shrink-0 md:[@media(min-height:900px)]:block">
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
