"use client";

import React from 'react';
import { SunIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { StatusHero } from '../components/UI/StatusHero';
import { KpiRow } from '../components/UI/KpiRow';
import { GhiForecastChart } from '../components/UI/GhiForecastChart';
import { PowerForecastChart } from '../components/UI/PowerForecastChart';
import { CloudPanel } from '../components/UI/CloudPanel';
import { ForecastFreshness } from '../components/UI/ForecastFreshness';

/**
 * First screen for the operator: what to do now (status), the three numbers behind it,
 * then the two forecasts and the cloud cover. Lists and tools live on their own pages.
 */
export function Dashboard() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2">
        <SunIcon className="h-9 w-9 text-sun" strokeWidth={2.2} />
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('solar_forecast_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('solar_forecast_desc')}</p>
        </div>
        <ForecastFreshness />
      </div>

      <StatusHero />
      <KpiRow />

      <div className="grid min-h-[250px] flex-1 grid-cols-1 gap-3.5 xl:grid-cols-[1.25fr_1fr] [&>*]:min-h-[250px]">
        <GhiForecastChart />
        <CloudPanel />
      </div>
      <div className="h-[210px] shrink-0">
        <PowerForecastChart />
      </div>
    </div>
  );
}
