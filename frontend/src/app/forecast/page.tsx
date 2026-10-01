"use client";

import React from 'react';
import { LineChartIcon, SunIcon, TrendingUpIcon, CloudSunIcon, AlertTriangleIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { GhiForecastChart } from '@/components/UI/GhiForecastChart';
import { PowerForecastChart } from '@/components/UI/PowerForecastChart';
import { CloudMovement } from '@/components/UI/CloudMovement';
import { useForecast } from '@/context/ForecastContext';

export default function ForecastPage() {
  const t = useTranslations('common');
  const { modelMeta, chartGhiData } = useForecast();

  // Find peak predicted GHI from active time-series curve
  const peakGhi = chartGhiData.length > 0 
    ? Math.max(...chartGhiData.map(d => d.predicted)) 
    : 790;
  const peakPoint = chartGhiData.find(d => d.predicted === peakGhi);

  const r2Pct = (modelMeta.test_metrics.r2 * 100).toFixed(1);
  const maeVal = modelMeta.test_metrics.mae.toFixed(1);

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sun/15 text-sun">
            <LineChartIcon className="h-6 w-6 text-sun" strokeWidth={2.2} />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('forecast_page_title')}</h1>
              <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-600 border border-emerald-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                ONNX Model ({modelMeta.forecast_steps} steps / {modelMeta.resolution_minutes}m)
              </span>
            </div>
            <p className="text-[13.5px] text-slate-600">{t('forecast_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Model Accuracy Highlights */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
            <TrendingUpIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('ghi_model_name')}</p>
            <p className="text-[24px] font-bold text-ink">{r2Pct}% <span className="text-[14px] font-normal text-ok">R² Score</span></p>
            <p className="text-[11.5px] text-muted">MAE: {maeVal} W/m² (144 in → 18 out)</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <CloudSunIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('cloud_tracker_name')}</p>
            <p className="text-[24px] font-bold text-ink">91.8% <span className="text-[14px] font-normal text-ok">Accuracy</span></p>
            <p className="text-[11.5px] text-muted">Himawari-8/9 Satellite Frame</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-sun/15 text-sun">
            <SunIcon className="h-5 w-5 text-sun" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('peak_ghi_predicted')}</p>
            <p className="text-[24px] font-bold text-ink">{peakGhi} <span className="text-[14px] font-normal text-muted">W/m²</span></p>
            <p className="text-[11.5px] text-muted">{peakPoint ? `${t('at_time')} ${peakPoint.t}` : t('peak_ghi_time')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warn-soft text-warn">
            <AlertTriangleIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('steepest_drop')}</p>
            <p className="text-[24px] font-bold text-warn">-48% <span className="text-[14px] font-normal text-muted">{t('per_hour')}</span></p>
            <p className="text-[11.5px] text-muted">{t('steepest_drop_time')}</p>
          </div>
        </article>
      </div>

      {/* Main Charts Grid */}
      <div className="grid grid-cols-2 gap-3.5 h-[340px]">
        <GhiForecastChart />
        <PowerForecastChart />
      </div>

      {/* Cloud Movement Detailed */}
      <div className="h-[250px]">
        <CloudMovement />
      </div>
    </div>
  );
}
