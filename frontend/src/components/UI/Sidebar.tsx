"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  HomeIcon,
  MapPinIcon,
  LineChartIcon,
  LightbulbIcon,
  BellIcon,
} from 'lucide-react';

const items = [
  { id: 'dashboard', key: 'nav_dashboard' as const, icon: HomeIcon, href: '/' },
  { id: 'stations', key: 'nav_stations' as const, icon: MapPinIcon, href: '/stations' },
  { id: 'forecast', key: 'nav_forecast' as const, icon: LineChartIcon, href: '/forecast' },
  { id: 'decision', key: 'nav_decision' as const, icon: LightbulbIcon, href: '/decision' },
  { id: 'alerts', key: 'nav_alerts' as const, icon: BellIcon, badge: 3, href: '/alerts' },
  // { id: 'models', key: 'nav_models' as const, icon: BrainIcon, href: '/models' },
  // { id: 'data', key: 'nav_data' as const, icon: DatabaseIcon, href: '/data' },
  // { id: 'jobs', key: 'nav_jobs' as const, icon: ListChecksIcon, href: '/jobs' },
  // { id: 'health', key: 'nav_health' as const, icon: ActivityIcon, href: '/health' },
];

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslations('common');

  return (
    <aside className="relative flex w-[64px] shrink-0 md:w-[230px] flex-col overflow-hidden border-r border-line bg-white shadow-sm">
      <nav aria-label="Main" className="flex flex-col gap-1 py-3">
        {items.map(({ id, key, icon: Icon, badge, href }) => {
          const isActive = pathname === href || (href !== '/' && pathname?.startsWith(href));
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
              {badge && (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-bad text-[11px] font-bold text-white">
                  {badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto hidden md:block">
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