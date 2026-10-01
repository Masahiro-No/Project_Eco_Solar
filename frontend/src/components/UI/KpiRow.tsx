"use client";

import React from 'react';
import { ZapIcon, TargetIcon, TriangleIcon, RadioTowerIcon } from 'lucide-react';
import { kpis, stations } from '@/data/dashboard';
import { useTranslations } from 'next-intl';

const icons: Record<string, { icon: React.ReactNode; bg: string }> = {
  pgen: { icon: <ZapIcon className="h-5 w-5 text-ok" fill="currentColor" />, bg: 'bg-ok-soft' },
  ptarget: { icon: <TargetIcon className="h-5 w-5 text-brand" />, bg: 'bg-brand-soft' },
  dp: { icon: <TriangleIcon className="h-5 w-5 text-ok" />, bg: 'bg-ok-soft' },
};

const labelMap: Record<string, string> = {
  pgen: 'kpi_pgen',
  ptarget: 'kpi_ptarget',
  dp: 'kpi_dp',
};

const noteMap: Record<string, string> = {
  pgen: 'compare_1h',
  ptarget: 'constant',
  dp: 'more_reserve',
};

export function KpiRow() {
  const t = useTranslations('common');
  const online = stations.filter((s) => s.online).length;

  return (
    <div className="grid shrink-0 grid-cols-4 gap-3.5">
      {kpis.map((k) => (
        <article key={k.id} className="flex gap-3 rounded-xl border border-line bg-white px-3.5 py-3 shadow-sm">
          <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${icons[k.id].bg}`}>
            {icons[k.id].icon}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-[13px] font-medium text-slate-600">
              {labelMap[k.id] ? t(labelMap[k.id] as any) : k.label}
            </h3>
            <div className="mt-1 flex items-end justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[25px] font-bold leading-none text-ink">
                  {k.value} <span className="text-[15px] font-medium text-slate-600">{k.unit}</span>
                </p>
                <p className="mt-1.5 truncate text-[12px] text-muted">
                  {k.delta && (
                    <span className="mr-1.5 font-bold text-ok">
                      {k.trend === 'up' ? '▲' : '▼'} {k.delta}
                    </span>
                  )}
                  {noteMap[k.id] ? t(noteMap[k.id] as any) : k.note}
                </p>
              </div>
              <Sparkline points={k.spark} color={k.tone === 'brand' ? '#3b82f6' : '#16a34a'} />
            </div>
          </div>
        </article>
      ))}
      <article className="flex gap-3 rounded-xl border border-line bg-white px-3.5 py-3 shadow-sm">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft">
          <RadioTowerIcon className="h-5 w-5 text-ok" />
        </span>
        <div className="flex-1">
          <h3 className="text-[13px] font-medium text-slate-600">{t('kpi_online_stations')}</h3>
          <div className="mt-1 flex items-end justify-between">
            <div>
              <p className="text-[25px] font-bold leading-none text-ink">
                {online} <span className="text-[15px] font-medium text-slate-500">/ {stations.length}</span>
              </p>
              <p className="mt-1.5 text-[12px] text-muted">{t('online')}</p>
            </div>
            <div className="flex items-end gap-1.5" aria-label={`${online} of ${stations.length} stations online`}>
              {stations.map((s, i) => (
                <span
                  key={s.id}
                  className={`w-2.5 rounded-sm ${s.online ? 'bg-ok' : 'bg-slate-200'}`}
                  style={{ height: [16, 20, 24, 20, 24][i] }}
                />
              ))}
            </div>
          </div>
        </div>
      </article>
    </div>
  );
}

function Sparkline({ points, color }: { points: number[]; color: string }) {
  const w = 72;
  const h = 28;
  const max = 60;
  const step = w / (points.length - 1);
  const path = points.map((p, i) => `${i * step},${h - (p / max) * h}`).join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="shrink-0">
      <polyline points={`0,${h} ${path} ${w},${h}`} fill={color} opacity={0.08} />
      <polyline points={path} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
    </svg>
  );
}