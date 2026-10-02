"use client";

import React from 'react';
import { LightbulbIcon, AlertCircleIcon, ShieldAlertIcon, CheckCircle2Icon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { useForecast } from '@/context/ForecastContext';

export function DecisionSupport() {
  const t = useTranslations('common');
  const { prediction, selectedStation } = useForecast();

  const pgenNum = prediction?.estimated_power_kw ?? 3377;
  const ptargetNum = prediction?.target_power_kw ?? (selectedStation?.target_capacity_kw ?? 5000);
  const deltaPNum = prediction?.delta_p_kw ?? (ptargetNum - pgenNum);
  const alertLevel = prediction?.alert_level ?? 'Critical Alert';
  const recommendation = prediction?.recommendation_text ?? t('reason_detail');
  const cloudTrend = prediction?.cloud_trend ?? 'Inward';

  const pct = ptargetNum > 0 ? Math.round((pgenNum / ptargetNum) * 100) : 0;

  const metrics = [
    {
      label: 'P_gen',
      value: Math.round(pgenNum).toLocaleString(),
      color: 'text-ok',
      note: `${pct}% ${t('pct_of_target')}`,
    },
    {
      label: 'P_target',
      value: Math.round(ptargetNum).toLocaleString(),
      color: 'text-ink',
      note: t('set_target'),
    },
    {
      label: 'ΔP',
      value: Math.round(Math.abs(deltaPNum)).toLocaleString(),
      color: deltaPNum > 0 ? 'text-bad font-bold' : 'text-ok font-bold',
      note: deltaPNum > 0 ? t('reserve_more') : 'กำลังผลิตเกินเป้า',
    },
  ];

  const isCritical = alertLevel.toLowerCase().includes('critical');
  const isWarning = alertLevel.toLowerCase().includes('warning') || alertLevel.toLowerCase().includes('early');

  return (
    <Panel
      title={t('decision_support_title')}
      icon={<LightbulbIcon className="h-5 w-5 text-slate-700" />}
      className="flex-1"
    >
      {/* Alert Banner */}
      <div
        role="alert"
        className={`flex shrink-0 items-center gap-3 rounded-lg border px-3.5 py-2.5 transition-colors ${
          isCritical
            ? 'border-red-300 bg-bad-soft text-bad'
            : isWarning
            ? 'border-warn/30 bg-warn-soft text-[#b45309]'
            : 'border-ok/30 bg-ok-soft text-ok'
        }`}
      >
        {isCritical ? (
          <ShieldAlertIcon className="h-7 w-7 shrink-0 text-bad" />
        ) : isWarning ? (
          <AlertCircleIcon className="h-7 w-7 shrink-0 fill-warn text-white" />
        ) : (
          <CheckCircle2Icon className="h-7 w-7 shrink-0 text-ok" />
        )}
        <div className="min-w-0">
          <p className="truncate text-[15px] font-bold">
            {alertLevel} ({cloudTrend} Sky)
          </p>
          <p className="text-[12.5px] font-medium leading-snug">
            {isCritical ? 'แจ้งเตือนเร่งสำรองไฟฉุกเฉิน BESS ทันที' : t('prepare_reserve')}
          </p>
        </div>
      </div>

      {/* Metrics Row */}
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

      {/* Decision Engine Recommendation Reason */}
      <div className="mt-2.5 min-h-0 flex-1 overflow-hidden rounded-lg bg-canvas px-3.5 py-2.5 border border-slate-100">
        <p className="text-[12px] font-bold text-ink">{t('reason')}</p>
        <p className="mt-1 text-[12px] leading-[20px] text-slate-700 font-medium line-clamp-3">
          {recommendation}
        </p>
      </div>
    </Panel>
  );
}