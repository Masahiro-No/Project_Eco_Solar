"use client";

import React from 'react';
import { LightbulbIcon, AlertCircleIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';

export function DecisionSupport() {
  const t = useTranslations('common');

  const metrics = [
    { label: 'P_gen', value: '742', color: 'text-ok', note: `87% ${t('pct_of_target')}` },
    { label: 'P_target', value: '850', color: 'text-ink', note: t('set_target') },
    { label: 'ΔP', value: '108', color: 'text-warn', note: t('reserve_more') },
  ];

  return (
    <Panel
      title={t('decision_support_title')}
      icon={<LightbulbIcon className="h-5 w-5 text-slate-700" />}
      className="flex-1"
    >
      <div role="alert" className="flex shrink-0 items-center gap-3 rounded-lg border border-warn/30 bg-warn-soft px-3.5 py-2.5">
        <AlertCircleIcon className="h-7 w-7 shrink-0 fill-warn text-white" />
        <div className="min-w-0">
          <p className="truncate text-[16px] font-bold text-[#b45309]">{t('cloud_alert_warning')}</p>
          <p className="text-[13px] font-medium text-[#b45309]">{t('prepare_reserve')}</p>
        </div>
      </div>
      <div className="mt-2.5 grid shrink-0 grid-cols-3 gap-2">
        {metrics.map((m) => (
          <div key={m.label} className="rounded-lg border border-line px-2.5 py-2">
            <p className="text-[12px] font-medium text-slate-600">{m.label}</p>
            <p className={`text-[19px] font-bold leading-tight ${m.color}`}>
              {m.value} <span className="text-[13px] font-semibold">kW</span>
            </p>
            <p className="truncate text-[11px] font-medium text-muted">{m.note}</p>
          </div>
        ))}
      </div>
      <div className="mt-2.5 min-h-0 flex-1 overflow-hidden rounded-lg bg-canvas px-3.5 py-2.5">
        <p className="text-[12px] font-bold text-ink">{t('reason')}</p>
        <p className="mt-1 text-[12px] leading-[20px] text-slate-600 font-medium">
          {t('reason_detail')}
        </p>
      </div>
    </Panel>
  );
}