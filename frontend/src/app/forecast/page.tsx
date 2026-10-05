"use client";

import React from 'react';
import { LineChartIcon, TableIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { GhiForecastChart } from '@/components/UI/GhiForecastChart';
import { PowerForecastChart } from '@/components/UI/PowerForecastChart';
import { CloudPanel } from '@/components/UI/CloudPanel';
import { ForecastFreshness } from '@/components/UI/ForecastFreshness';
import { Panel } from '@/components/UI/Panel';
import { useForecast } from '@/context/ForecastContext';
import { CLOUD_UI, impactLevelOfLoss } from '@/lib/levels';

export default function ForecastPage() {
  const t = useTranslations('common');
  const { chartGhiData, chartPowerData, prediction } = useForecast();

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sun/15 text-sun">
          <LineChartIcon className="h-6 w-6 text-sun" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('forecast_page_title')}</h1>
          <p className="text-[13.5px] text-slate-600">
            {t('forecast_page_desc')}
            {prediction?.model_version ? ` · ${t('model_version')} ${prediction.model_version}` : ''}
          </p>
        </div>
        <ForecastFreshness />
      </div>

      <div className="grid shrink-0 grid-cols-1 gap-3.5 xl:grid-cols-2 [&>*]:h-[300px]">
        <GhiForecastChart />
        <PowerForecastChart />
      </div>

      <div className="h-[270px] shrink-0">
        <CloudPanel />
      </div>

      {/* The same forecast as numbers, for reading exact values */}
      <Panel title={t('forecast_table_title')} icon={<TableIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        {chartGhiData.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-muted">{t('no_forecast_title')}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-right text-[13px] tabular-nums">
              <thead className="border-b border-line bg-canvas font-bold text-slate-700">
                <tr>
                  <th className="px-3 py-2 text-left">{t('th_time')}</th>
                  <th className="px-3 py-2">{t('ghi_lstm')} (W/m²)</th>
                  <th className="px-3 py-2">{t('ghi_blend')} (W/m²)</th>
                  <th className="px-3 py-2">{t('band_legend')}</th>
                  <th className="px-3 py-2">{t('ghi_weight')}</th>
                  <th className="px-3 py-2">{t('cloud_cover')}</th>
                  <th className="px-3 py-2">{t('sat_loss_col')}</th>
                  <th className="px-3 py-2">{t('kpi_pgen')} (kW)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white text-slate-700">
                {chartGhiData.map((p, i) => {
                  const lv = impactLevelOfLoss(p.lossPct);
                  return (
                    <tr key={p.t}>
                      <td className="px-3 py-1.5 text-left font-medium text-ink">{p.t}</td>
                      <td className="px-3 py-1.5">{p.lstm ?? '—'}</td>
                      <td className="px-3 py-1.5 font-semibold text-ink">{p.blend}</td>
                      <td className="px-3 py-1.5">{p.band ? `${p.band[0]}–${p.band[1]}` : '—'}</td>
                      <td className="px-3 py-1.5">{p.weightPct === null ? '—' : `${p.weightPct}%`}</td>
                      <td className="px-3 py-1.5">{p.cloudPct === null ? '—' : `${p.cloudPct}%`}</td>
                      <td className="px-3 py-1.5">
                        {p.lossPct === null || !lv ? '—' : `${p.lossPct}% · ${t(CLOUD_UI[lv].labelKey)}`}
                      </td>
                      <td className="px-3 py-1.5">{chartPowerData[i] ? chartPowerData[i].gen.toLocaleString() : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
