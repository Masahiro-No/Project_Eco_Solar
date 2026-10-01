"use client";

import React from 'react';
import Link from 'next/link';
import { BellIcon, AlertCircleIcon, InfoIcon, CheckCircle2Icon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { alerts } from '@/data/dashboard';

const levelStyles = {
  Warning: { pill: 'bg-warn-soft text-warn', icon: <AlertCircleIcon className="h-4 w-4 fill-warn text-white" /> },
  Critical: { pill: 'bg-bad-soft text-bad', icon: <AlertCircleIcon className="h-4 w-4 fill-bad text-white" /> },
  Info: { pill: 'bg-brand-soft text-brand', icon: <InfoIcon className="h-4 w-4 fill-brand text-white" /> },
  Normal: { pill: 'bg-ok-soft text-ok', icon: <CheckCircle2Icon className="h-4 w-4 fill-ok text-white" /> },
};

export function RecentAlerts() {
  const t = useTranslations('common');

  return (
    <Panel
      title={t('recent_alerts_title')}
      icon={<BellIcon className="h-5 w-5 text-[#1e3a8a]" />}
      className="flex-1"
      action={
        <Link href="/alerts" className="whitespace-nowrap text-[12px] font-semibold text-brand hover:underline">
          {t('view_all')}
        </Link>
      }
    >
      <ul className="min-h-0 flex-1 overflow-y-auto pr-1">
        {alerts.map((a) => {
          const s = levelStyles[a.level];
          return (
            <li key={a.id} className="flex items-start gap-2.5 border-b border-line py-2 first:pt-0 last:border-0">
              <span className="mt-0.5 shrink-0">{s.icon}</span>
              <span className={`w-[60px] shrink-0 rounded-full py-0.5 text-center text-[11px] font-bold ${s.pill}`}>
                {a.level}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] font-semibold text-ink">{a.title}</p>
                <p className="truncate text-[11px] text-muted">{a.station}</p>
              </div>
              <span className="text-[11px] tabular-nums font-medium text-slate-600">{a.time}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}