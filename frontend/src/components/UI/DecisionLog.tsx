"use client";

import React from 'react';
import { HistoryIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { decisionLog } from '@/data/dashboard';

export function DecisionLog() {
  const t = useTranslations('common');

  return (
    <Panel
      title={t('decision_log_title')}
      icon={<HistoryIcon className="h-5 w-5 text-[#1e3a8a]" />}
      className="shrink-0"
    >
      <ul className="rounded-lg border border-line">
        {decisionLog.map((d, i) => (
          <li
            key={d.id}
            className="flex items-center gap-2.5 border-b border-line px-3 py-2 last:border-0 hover:bg-slate-50/60"
          >
            <span className="flex h-5.5 w-5.5 shrink-0 items-center justify-center rounded-full bg-warn text-[11px] font-bold text-white">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] font-semibold text-ink">{d.action}</p>
              <p className="truncate text-[11px] font-medium text-slate-600">{d.station}</p>
            </div>
            <span className="text-[11px] tabular-nums font-medium text-muted">{d.time}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}