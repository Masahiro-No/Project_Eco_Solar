"use client";

import React from 'react';
import { LeafIcon } from 'lucide-react';
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { powerData } from '@/data/dashboard';

export function PowerForecastChart() {
  const t = useTranslations('common');

  return (
    <Panel
      title={t('power_forecast_title')}
      icon={<LeafIcon className="h-5 w-5 text-ok" fill="#bbf7d0" />}
      className="flex-1"
    >
      <div className="-mt-0.5 mb-1 flex shrink-0 items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-slate-600">{t('power_unit')}</p>
        <div className="flex items-center gap-3 text-[11.5px] text-slate-600">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-0.5 w-4 bg-ok" /> P_gen
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="w-4 border-t-2 border-dashed border-brand-mid" /> P_target
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-2 w-4 bg-brand-soft" /> {t('reserve_gap')}
          </span>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={powerData} margin={{ top: 6, right: 6, left: -16, bottom: -4 }}>
            <CartesianGrid stroke="#eef2f7" />
            <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={{ stroke: '#cbd5e1' }} />
            <YAxis
              domain={[0, 1000]}
              ticks={[0, 250, 500, 750, 1000]}
              tick={{ fontSize: 11, fill: '#475569' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => v.toLocaleString()}
            />
            <Tooltip contentStyle={{ fontSize: 12.5, borderRadius: 8, borderColor: '#e3e9f2' }} />
            <Area dataKey="gap" name={t('reserve_gap')} stroke="none" fill="#3b82f6" fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="target" name="P_target" stroke="#3b82f6" strokeWidth={1.6} strokeDasharray="7 5" dot={false} />
            <Line dataKey="gen" name="P_gen" stroke="#16a34a" strokeWidth={2} dot={{ r: 3, fill: '#16a34a' }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}