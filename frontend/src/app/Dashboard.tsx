"use client";

import React from 'react';
import { SunIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { KpiRow } from '../components/UI/KpiRow';
import { GhiForecastChart } from '../components/UI/GhiForecastChart';
import { CloudMovement } from '../components/UI/CloudMovement';
import { PowerForecastChart } from '../components/UI/PowerForecastChart';
import { StationTable } from '../components/UI/StationTable';
import { DecisionSupport } from '../components/UI/DecisionSupport';
import { DecisionLog } from '../components/UI/DecisionLog';
import { RecentAlerts } from '../components/UI/RecentAlerts';
import { ServiceStatus } from '../components/UI/ServiceStatus';

export function Dashboard() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 items-center gap-3">
        <SunIcon className="h-9 w-9 text-sun" strokeWidth={2.2} />
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('solar_forecast_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('solar_forecast_desc')}</p>
        </div>
      </div>

      <KpiRow />

      <div className="grid h-[225px] shrink-0 grid-cols-[1fr_1.35fr] gap-3.5">
        <GhiForecastChart />
        <CloudMovement />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[1.3fr_1fr_0.95fr] gap-3.5">
        <div className="flex min-h-0 flex-col gap-2.5">
          <PowerForecastChart />
          <StationTable />
        </div>
        <div className="flex min-h-0 flex-col gap-2.5">
          <DecisionSupport />
          <DecisionLog />
        </div>
        <div className="flex min-h-0 flex-col gap-2.5">
          <RecentAlerts />
          <ServiceStatus />
        </div>
      </div>
    </div>
  );
}