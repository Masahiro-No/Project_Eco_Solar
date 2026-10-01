"use client";

import React, { useState } from 'react';
import { BellIcon, AlertCircleIcon, InfoIcon, CheckCircle2Icon, SearchIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { alerts } from '@/data/dashboard';
import { Panel } from '@/components/UI/Panel';

const fullAlerts = [
  ...alerts,
  { id: 6, level: 'Warning' as const, title: 'อุณหภูมิแผงโซลาร์สูงเกิน 60°C', station: 'Songkhla Solar Farm', time: '13:45' },
  { id: 7, level: 'Critical' as const, title: 'Inverter #3 ขาดการเชื่อมต่อ', station: 'Pattani Solar Farm', time: '11:20' },
  { id: 8, level: 'Normal' as const, title: 'การตรวจสอบระบบประจำวันผ่านทุกรายการ', station: 'Trang Solar Farm', time: '09:00' },
];

const levelStyles = {
  Warning: { pill: 'bg-warn-soft text-warn border-warn/30', icon: <AlertCircleIcon className="h-4.5 w-4.5 fill-warn text-white" /> },
  Critical: { pill: 'bg-bad-soft text-bad border-bad/30', icon: <AlertCircleIcon className="h-4.5 w-4.5 fill-bad text-white" /> },
  Info: { pill: 'bg-brand-soft text-brand border-brand/30', icon: <InfoIcon className="h-4.5 w-4.5 fill-brand text-white" /> },
  Normal: { pill: 'bg-ok-soft text-ok border-ok/30', icon: <CheckCircle2Icon className="h-4.5 w-4.5 fill-ok text-white" /> },
};

export default function AlertsPage() {
  const t = useTranslations('common');
  const [filter, setFilter] = useState<'All' | 'Critical' | 'Warning' | 'Info' | 'Normal'>('All');
  const [search, setSearch] = useState('');

  const filteredAlerts = fullAlerts.filter((a) => {
    const matchesFilter = filter === 'All' || a.level === filter;
    const matchesSearch = a.title.toLowerCase().includes(search.toLowerCase()) || a.station.toLowerCase().includes(search.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-bad-soft text-bad">
            <BellIcon className="h-6 w-6 text-bad" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('alerts_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('alerts_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Main Alerts List */}
      <Panel title={`${t('all_alerts_count')} (${filteredAlerts.length})`} icon={<BellIcon className="h-5 w-5 text-bad" />}>
        {/* Controls */}
        <div className="mb-3.5 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder={t('search_alert_placeholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-9.5 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13.5px] text-ink placeholder:text-muted focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft"
            />
          </div>

          <div className="flex items-center gap-1.5 rounded-lg border border-line bg-canvas p-1 text-[12.5px] font-medium">
            {(['All', 'Critical', 'Warning', 'Info', 'Normal'] as const).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setFilter(lvl)}
                className={`rounded-md px-3 py-1 transition-colors ${
                  filter === lvl ? 'bg-white shadow-sm font-bold text-ink' : 'text-slate-600 hover:text-ink'
                }`}
              >
                {lvl === 'All' ? t('filter_all') : lvl}
              </button>
            ))}
          </div>
        </div>

        {/* Alerts Table */}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('level')}</th>
                <th className="px-4 py-3">{t('event_details')}</th>
                <th className="px-4 py-3">{t('station')}</th>
                <th className="px-4 py-3 text-right">{t('occurred_time')}</th>
                <th className="px-4 py-3 text-center">{t('action_management')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {filteredAlerts.map((a) => {
                const s = levelStyles[a.level];
                return (
                  <tr key={a.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-bold ${s.pill}`}>
                        {s.icon}
                        {a.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-ink">{a.title}</td>
                    <td className="px-4 py-3 text-slate-600 font-medium">{a.station}</td>
                    <td className="px-4 py-3 text-right font-medium text-slate-500 tabular-nums">{a.time}</td>
                    <td className="px-4 py-3 text-center">
                      <button className="rounded-lg border border-line bg-white px-2.5 py-1 text-[12px] font-semibold text-slate-700 hover:bg-canvas">
                        {t('acknowledge')}
                      </button>
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
