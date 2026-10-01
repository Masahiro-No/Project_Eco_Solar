"use client";

import React from 'react';
import Link from 'next/link';
import { MapPinIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { stations } from '@/data/dashboard';

export function StationTable() {
  const t = useTranslations('common');

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
            <th className="w-8 rounded-l-md px-2.5 py-2 font-bold">{t('th_id')}</th>
            <th className="px-2.5 py-2 font-bold">{t('th_station_name')}</th>
            <th className="w-[58px] px-2.5 py-2 text-right font-bold">{t('th_pgen')}</th>
            <th className="w-[66px] px-2.5 py-2 text-right font-bold">{t('th_ptarget')}</th>
            <th className="w-[50px] px-2.5 py-2 text-right font-bold">{t('th_dp')}</th>
            <th className="w-[78px] rounded-r-md px-2.5 py-2 font-bold">{t('th_status')}</th>
          </tr>
        </thead>
        <tbody>
          {stations.slice(0, 4).map((s) => {
            const dp = s.ptarget - s.pgen;
            return (
              <tr key={s.id} className="border-b border-line last:border-0 hover:bg-slate-50/60">
                <td className="px-2.5 py-2 text-slate-600 font-medium">{s.id}</td>
                <td className="truncate px-2.5 py-2 font-medium text-ink" title={s.name}>
                  {s.name}
                </td>
                <td className="px-2.5 py-2 text-right tabular-nums">{s.online ? s.pgen : '—'}</td>
                <td className="px-2.5 py-2 text-right tabular-nums">{s.ptarget}</td>
                <td
                  className={`px-2.5 py-2 text-right font-semibold tabular-nums ${
                    !s.online ? 'text-muted' : dp > 0 ? 'text-warn' : 'text-ok'
                  }`}
                >
                  {s.online ? (dp > 0 ? `${dp}` : `+${-dp}`) : '—'}
                </td>
                <td className="px-2.5 py-2">
                  <span
                    className={`inline-flex items-center gap-1.5 whitespace-nowrap font-medium ${
                      s.online ? 'text-ok' : 'text-muted'
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full ${s.online ? 'bg-ok' : 'bg-slate-300'}`} />
                    {s.online ? t('online') : t('offline')}
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