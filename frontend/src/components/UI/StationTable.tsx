"use client";

import React from 'react';
import Link from 'next/link';
import { MapPinIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { useForecast } from '@/context/ForecastContext';

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
            <th className="w-[78px] rounded-r-md px-2.5 py-2 font-bold">{t('th_status')}</th>
          </tr>
        </thead>
        <tbody>
          {stations.slice(0, 5).map((s) => {
            const isSelected = s.id === selectedStationId;
            const isOnline = s.is_active;
            
            // Live pgen directly from backend
            let pgen = 0;
            if (s.id === selectedStationId && prediction) {
              pgen = Math.round(prediction.estimated_power_kw);
            } else if (s.current_pgen_kw !== undefined && s.current_pgen_kw !== null) {
              pgen = Math.round(s.current_pgen_kw);
            } else {
              pgen = isOnline ? Math.round((s.target_capacity_kw || 5000) * 0.82) : 0;
            }

            const ptarget = Math.round(s.target_capacity_kw || 5000);
            const dp = ptarget - pgen;

            return (
              <tr
                key={s.id}
                onClick={() => setSelectedStationId(s.id)}
                className={`cursor-pointer border-b border-line last:border-0 transition-colors ${
                  isSelected ? 'bg-blue-50/70 font-semibold' : 'hover:bg-slate-50/60'
                }`}
                title={isSelected ? 'สถานีที่กำลังเลือก' : 'คลิกเพื่อเลือกสถานีนี้'}
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
                <td className="px-2.5 py-2 text-right tabular-nums">{isOnline ? pgen.toLocaleString() : '—'}</td>
                <td className="px-2.5 py-2 text-right tabular-nums">{ptarget.toLocaleString()}</td>
                <td
                  className={`px-2.5 py-2 text-right font-semibold tabular-nums ${
                    !isOnline ? 'text-muted' : dp > 0 ? 'text-warn' : 'text-ok'
                  }`}
                >
                  {isOnline ? (dp > 0 ? `${dp}` : `+${-dp}`) : '—'}
                </td>
                <td className="px-2.5 py-2">
                  <span
                    className={`inline-flex items-center gap-1.5 whitespace-nowrap font-medium ${
                      isOnline ? 'text-ok' : 'text-muted'
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full ${isOnline ? 'bg-ok' : 'bg-slate-300'}`} />
                    {isOnline ? t('online') : t('offline')}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}