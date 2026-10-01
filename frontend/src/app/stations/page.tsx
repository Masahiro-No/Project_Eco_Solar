"use client";

import React, { useState } from 'react';
import { MapPinIcon, RadioTowerIcon, ZapIcon, CheckCircle2Icon, SearchIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';

const stationDetails = [
  { id: 1, name: 'Hat Yai Solar Farm', province: 'สงขลา', capacity: '1,000 kWp', pgen: 742, ptarget: 850, online: true, inverters: '8/8', pr: '86.4%', temp: '32.5°C' },
  { id: 2, name: 'Songkhla Solar Farm', province: 'สงขลา', capacity: '800 kWp', pgen: 612, ptarget: 650, online: true, inverters: '6/6', pr: '84.2%', temp: '33.1°C' },
  { id: 3, name: 'Nakhon Si Thammarat Solar Farm', province: 'นครศรีธรรมราช', capacity: '600 kWp', pgen: 530, ptarget: 500, online: true, inverters: '5/5', pr: '88.1%', temp: '31.8°C' },
  { id: 4, name: 'Pattani Solar Farm', province: 'ปัตตานี', capacity: '500 kWp', pgen: 0, ptarget: 400, online: false, inverters: '0/4', pr: '—', temp: '34.0°C' },
  { id: 5, name: 'Trang Solar Farm', province: 'ตรัง', capacity: '550 kWp', pgen: 0, ptarget: 450, online: false, inverters: '0/5', pr: '—', temp: '31.2°C' },
];

export default function StationsPage() {
  const t = useTranslations('common');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'online' | 'offline'>('all');

  const filtered = stationDetails.filter(s => {
    const matchesSearch = s.name.toLowerCase().includes(searchTerm.toLowerCase()) || s.province.includes(searchTerm);
    const matchesStatus = filterStatus === 'all' || (filterStatus === 'online' ? s.online : !s.online);
    return matchesSearch && matchesStatus;
  });

  const totalPgen = stationDetails.reduce((sum, s) => sum + s.pgen, 0);
  const totalTarget = stationDetails.reduce((sum, s) => sum + s.ptarget, 0);
  const onlineCount = stationDetails.filter(s => s.online).length;

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <MapPinIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('stations_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('stations_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
            <RadioTowerIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_stations')}</p>
            <p className="text-[25px] font-bold text-ink">
              {stationDetails.length} <span className="text-[15px] font-normal text-muted">{t('unit_station')}</span>
            </p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <CheckCircle2Icon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('online_status')}</p>
            <p className="text-[25px] font-bold text-ok">
              {onlineCount} <span className="text-[15px] font-normal text-slate-500">/ {stationDetails.length}</span>
            </p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <ZapIcon className="h-5 w-5" fill="currentColor" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_current_pgen')}</p>
            <p className="text-[25px] font-bold text-ink">
              {totalPgen.toLocaleString()} <span className="text-[15px] font-normal text-muted">kW</span>
            </p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
            <ZapIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_target_pgen')}</p>
            <p className="text-[25px] font-bold text-ink">
              {totalTarget.toLocaleString()} <span className="text-[15px] font-normal text-muted">kW</span>
            </p>
          </div>
        </article>
      </div>

      {/* Main Table Panel */}
      <Panel title={t('station_list_title')} icon={<MapPinIcon className="h-5 w-5 text-brand" />}>
        {/* Filter Toolbar */}
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder={t('search_station_placeholder')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-9.5 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13.5px] text-ink placeholder:text-muted focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-slate-600">{t('filter_status')}</span>
            <div className="flex rounded-lg border border-line bg-canvas p-0.5 text-[12.5px] font-medium">
              <button
                onClick={() => setFilterStatus('all')}
                className={`rounded-md px-3 py-1 transition-colors ${filterStatus === 'all' ? 'bg-white shadow-sm font-semibold text-brand' : 'text-slate-600 hover:text-ink'}`}>
                {t('filter_all')}
              </button>
              <button
                onClick={() => setFilterStatus('online')}
                className={`rounded-md px-3 py-1 transition-colors ${filterStatus === 'online' ? 'bg-white shadow-sm font-semibold text-ok' : 'text-slate-600 hover:text-ink'}`}>
                {t('online')} ({onlineCount})
              </button>
              <button
                onClick={() => setFilterStatus('offline')}
                className={`rounded-md px-3 py-1 transition-colors ${filterStatus === 'offline' ? 'bg-white shadow-sm font-semibold text-bad' : 'text-slate-600 hover:text-ink'}`}>
                {t('offline')} ({stationDetails.length - onlineCount})
              </button>
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('th_id')}</th>
                <th className="px-4 py-3">{t('th_station_name')}</th>
                <th className="px-4 py-3">{t('th_province')}</th>
                <th className="px-4 py-3">{t('th_capacity')}</th>
                <th className="px-4 py-3 text-right">{t('th_pgen')} (kW)</th>
                <th className="px-4 py-3 text-right">{t('th_ptarget')} (kW)</th>
                <th className="px-4 py-3 text-right">{t('th_dp')}</th>
                <th className="px-4 py-3 text-center">{t('th_inverters')}</th>
                <th className="px-4 py-3 text-center">{t('th_pr')}</th>
                <th className="px-4 py-3 text-center">{t('th_status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {filtered.map((s) => {
                const dp = s.ptarget - s.pgen;
                return (
                  <tr key={s.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-500">{s.id}</td>
                    <td className="px-4 py-3 font-bold text-ink">{s.name}</td>
                    <td className="px-4 py-3 text-slate-600">{s.province}</td>
                    <td className="px-4 py-3 text-slate-600 font-medium">{s.capacity}</td>
                    <td className="px-4 py-3 text-right font-bold text-ink tabular-nums">{s.online ? s.pgen.toLocaleString() : '—'}</td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-600 tabular-nums">{s.ptarget.toLocaleString()}</td>
                    <td className={`px-4 py-3 text-right font-bold tabular-nums ${!s.online ? 'text-muted' : dp > 0 ? 'text-warn' : 'text-ok'}`}>
                      {s.online ? (dp > 0 ? `+${dp}` : `${dp}`) : '—'}
                    </td>
                    <td className="px-4 py-3 text-center text-slate-600 tabular-nums font-medium">{s.inverters}</td>
                    <td className="px-4 py-3 text-center text-slate-600 tabular-nums font-medium">{s.pr}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-bold ${s.online ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'}`}>
                        <span className={`h-2 w-2 rounded-full ${s.online ? 'bg-ok' : 'bg-bad'}`} />
                        {s.online ? t('online') : t('offline')}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
