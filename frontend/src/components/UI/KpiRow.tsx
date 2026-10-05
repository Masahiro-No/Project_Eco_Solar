"use client";

import React from 'react';
import { ZapIcon, TargetIcon, ScaleIcon, type LucideIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useForecast } from '@/context/ForecastContext';
import { InfoTip } from './InfoTip';

type Tile = {
  id: string;
  label: string;
  help: string;
  value: number | null;
  note: string;
  icon: LucideIcon;
};

/** Three numbers behind the decision. Icons are larger than the figures so the meaning reads first. */
export function KpiRow() {
  const t = useTranslations('common');
  const { prediction, selectedStation } = useForecast();

  const night = !!prediction?.is_night;
  const target = prediction?.target_power_kw ?? selectedStation?.target_capacity_kw ?? null;
  const pgen = prediction ? prediction.estimated_power_kw : null;
  // the target follows the sun: compare with what is expected at this time, not with the full dispatch target
  const targetNow = prediction?.target_profile_kw?.[0] ?? target;
  const pct = pgen !== null && targetNow ? Math.round((pgen / targetNow) * 100) : null;

  const tiles: Tile[] = [
    {
      id: 'pgen',
      label: t('kpi_pgen'),
      help: t('help_pgen'),
      value: pgen,
      note: night ? t('alert_night') : pct !== null ? `${pct}% ${t('pct_of_target')}` : t('no_data'),
      icon: ZapIcon,
    },
    {
      id: 'ptarget',
      label: t('kpi_ptarget'),
      help: t('help_ptarget'),
      value: target,
      note:
        prediction && !night && prediction.target_profile_kw?.length
          ? t('target_now_note', { kw: Math.round(prediction.target_profile_kw[0]).toLocaleString() })
          : selectedStation
          ? selectedStation.id
          : t('no_data'),
      icon: TargetIcon,
    },
    {
      id: 'dp',
      label: t('kpi_dp'),
      help: t('help_dp'),
      value: prediction ? prediction.delta_p_kw : null,
      note: !prediction ? t('no_data') : night ? t('alert_night') : prediction.delta_p_kw > 0 ? t('dp_short') : t('dp_met'),
      icon: ScaleIcon,
    },
  ];

  return (
    <div className="grid shrink-0 grid-cols-1 gap-3.5 sm:grid-cols-3">
      {tiles.map(({ id, label, help, value, note, icon: Icon }) => (
        <article key={id} className="flex items-center gap-4 rounded-xl border border-line bg-white px-4 py-3 shadow-sm">
          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-soft">
            <Icon className="h-9 w-9 text-brand" strokeWidth={2} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="flex items-center gap-1 text-[13.5px] font-medium text-slate-700">
              <span className="truncate">{label}</span>
              <InfoTip text={help} />
            </h3>
            <p className="text-[24px] font-bold leading-tight text-ink tabular-nums">
              {value === null ? '—' : Math.round(value).toLocaleString()}{' '}
              <span className="text-[14px] font-medium text-slate-600">kW</span>
            </p>
            <p className="truncate text-[12px] text-muted">{note}</p>
          </div>
        </article>
      ))}
    </div>
  );
}
