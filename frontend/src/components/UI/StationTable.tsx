"use client";

import React from 'react';
import Link from 'next/link';
import { MapPinIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { useForecast } from '@/context/ForecastContext';
import { alertUi, TONE_CLASS } from '@/lib/levels';

export function StationTable() {
  const t = useTranslations('common');
  const { stations, selectedStationId, setSelectedStationId, prediction } = useForecast();

  return (
    <Panel
      title={t('station_summary_title')}
      icon={<MapPinIcon className="h-5 w-5 text-[#1e3a8a]" />}
      className="shrink-0"
      action={
        <Link href="/stations" className="whitespace-nowrap text-[12px] font-semibold text-brand hover:underline">
          {t('view_all')}
        </Link>
      }
    >
      <table className="w-full table-fixed text-[12.5px]">
        <thead>
          <tr className="bg-canvas text-left text-slate-700">
            <th className="w-[64px] rounded-l-md px-2.5 py-2 font-bold">{t('th_id')}</th>
            <th className="px-2.5 py-2 font-bold">{t('th_station_name')}</th>
            <th className="w-[58px] px-2.5 py-2 text-right font-bold">{t('th_pgen')}</th>
            <th className="w-[66px] px-2.5 py-2 text-right font-bold">{t('th_ptarget')}</th>
            <th className="w-[50px] px-2.5 py-2 text-right font-bold">{t('th_dp')}</th>
            <th className="w-[170px] rounded-r-md px-2.5 py-2 font-bold">{t('th_status')}</th>
          </tr>
        </thead>
        <tbody>
          {stations.map((s) => {
            const isSelected = s.id === selectedStationId;
            const isOnline = s.is_active;
            
            // Live pgen directly from backend
            // null = no real measurement/forecast available (never fabricate a value)
            let pgen: number | null = null;
            if (s.id === selectedStationId && prediction) {
              pgen = Math.round(prediction.estimated_power_kw);
            } else if (s.current_pgen_kw !== undefined && s.current_pgen_kw !== null) {
              pgen = Math.round(s.current_pgen_kw);
            }

            const ptarget = Math.round(s.target_capacity_kw);
            // Alert level of the station's latest real forecast (the decision engine's result, not recomputed here)
            const level = s.id === selectedStationId && prediction ? prediction.alert_level : s.alert_level;
            const ui = isOnline ? alertUi(level) : null;
            const StatusIcon = ui?.icon;
            const isNight = level === 'night';
            // At night there is no production to compare with the target
            const hasPgen = isOnline && pgen !== null && !isNight;
            const dp = pgen !== null ? ptarget - pgen : 0;

            return (
              <tr
                key={s.id}
                onClick={() => setSelectedStationId(s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedStationId(s.id);
                  }
                }}
                tabIndex={0}
                aria-selected={isSelected}
                className={`cursor-pointer border-b border-line last:border-0 transition-colors ${
                  isSelected ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50/60'
                }`}
                title={isSelected ? t('station_selected_hint') : t('station_click_hint')}
              >
                <td className="px-2.5 py-2 font-medium text-slate-600">
                  <div className="flex items-center gap-1.5">
                    {isSelected && <span className="h-1.5 w-1.5 rounded-full bg-brand" />}
                    <span>{s.id}</span>
                  </div>
                </td>
                <td className="truncate px-2.5 py-2 font-medium text-ink" title={s.name}>
                  {s.name}
                </td>
                <td className="px-2.5 py-2 text-right tabular-nums">{isOnline && pgen !== null ? pgen.toLocaleString() : '—'}</td>
                <td className="px-2.5 py-2 text-right tabular-nums">{ptarget.toLocaleString()}</td>
                <td
                  className={`px-2.5 py-2 text-right font-semibold tabular-nums ${
                    !hasPgen ? 'text-muted' : dp > 0 ? 'text-warn' : 'text-ok'
                  }`}
                >
                  {hasPgen ? (dp > 0 ? `${dp}` : `+${-dp}`) : '—'}
                </td>
                <td className="px-2.5 py-2">
                  {ui && StatusIcon ? (
                    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-semibold ${TONE_CLASS[ui.tone].chip}`}>
                      <StatusIcon className="h-3.5 w-3.5" aria-hidden="true" />
                      {t(ui.labelKey)}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap font-medium text-muted">
                      <span className="h-2 w-2 rounded-full bg-slate-300" />
                      {isOnline ? t('no_forecast_short') : t('offline')}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}