"use client";

import React from 'react';
import { LineChartIcon, SunIcon, TrendingUpIcon, CloudSunIcon, AlertTriangleIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { GhiForecastChart } from '@/components/UI/GhiForecastChart';
import { PowerForecastChart } from '@/components/UI/PowerForecastChart';
import { CloudMovement } from '@/components/UI/CloudMovement';

export default function ForecastPage() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sun/15 text-sun">
            <LineChartIcon className="h-6 w-6 text-sun" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('forecast_page_title')}</h1>
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
            <p className="text-[24px] font-bold text-ink">95.4% <span className="text-[14px] font-normal text-ok">R² Score</span></p>
            <p className="text-[11.5px] text-muted">MAE: 24.5 W/m²</p>
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
            <p className="text-[24px] font-bold text-ink">790 <span className="text-[14px] font-normal text-muted">W/m²</span></p>
            <p className="text-[11.5px] text-muted">{t('peak_ghi_time')}</p>
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
