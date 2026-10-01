"use client";

import React from 'react';
import { SunIcon } from 'lucide-react';
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { ghiData } from '@/data/dashboard';
import { useForecast } from '@/context/ForecastContext';

export function GhiForecastChart() {
  const t = useTranslations('common');
  const { chartGhiData, isLive } = useForecast();
  const data = chartGhiData || ghiData;

  return (
    <Panel
      title={t('ghi_forecast_title')}
      icon={<SunIcon className="h-5 w-5 text-sun" />}
      className="h-full"
      action={
        <div className="flex items-center gap-3 text-[12px] text-slate-600">
          {isLive && (
            <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-bold text-emerald-600 border border-emerald-200">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              ONNX Model
            </span>
          )}
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-0.5 w-4 bg-brand" /> {t('actual')}
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="w-4 border-t-2 border-dashed border-brand-mid" /> {t('predicted_lstm')}
          </span>
        </div>
      }
    >
      <p className="shrink-0 text-[11px] font-semibold text-slate-600">{t('ghi_unit')}</p>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 6, right: 6, left: -20, bottom: -4 }}>
            <CartesianGrid stroke="#eef2f7" />
            <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={{ stroke: '#cbd5e1' }} interval={1} />
            <YAxis domain={[0, 1000]} ticks={[0, 200, 400, 600, 800, 1000]} tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ fontSize: 12.5, borderRadius: 8, borderColor: '#e3e9f2' }} />
            <Area dataKey="band" stroke="none" fill="#3b82f6" fillOpacity={0.12} name={t('confidence')} isAnimationActive={false} />
            <Line dataKey="predicted" name={t('predicted_lstm')} stroke="#3b82f6" strokeWidth={1.8} strokeDasharray="6 5" dot={{ r: 2.5, fill: '#fff', strokeWidth: 1.5 }} />
            <Line dataKey="actual" name={t('actual')} stroke="#1d4ed8" strokeWidth={2} dot={{ r: 3, fill: '#1d4ed8' }} connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}