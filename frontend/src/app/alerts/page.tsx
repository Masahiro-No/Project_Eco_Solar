"use client";

import React, { useCallback, useEffect, useState } from 'react';
import { BellIcon, CheckCircle2Icon, RefreshCwIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { StationTable } from '@/components/UI/StationTable';
import { AlertFeedItem, solarApi } from '@/services/api';
import { useForecast } from '@/context/ForecastContext';
import { TONE_CLASS, alertUi } from '@/lib/levels';
import { forecastTimeLabel } from '@/lib/time';

/** Stations whose latest model forecast needs attention. Nothing here is a sample: an empty list means no alert. */
export default function AlertsPage() {
  const t = useTranslations('common');
  const { setSelectedStationId, lastUpdated } = useForecast();
  const [alerts, setAlerts] = useState<AlertFeedItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const rows = await solarApi.getAlerts();
    setFailed(rows === null);
    setAlerts(rows ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load, lastUpdated]);

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-bad-soft text-bad">
          <BellIcon className="h-6 w-6 text-bad" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('alerts_page_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('alerts_page_desc')}</p>
        </div>
      </div>

      <Panel
        title={`${t('all_alerts_count')} (${alerts?.length ?? 0})`}
        icon={<BellIcon className="h-5 w-5 text-bad" />}
        className="shrink-0"
        action={
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 hover:bg-canvas disabled:opacity-40"
          >
            <RefreshCwIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </button>
        }
      >
        {failed ? (
          <p role="alert" className="py-6 text-center text-[13px] text-bad">{t('load_failed')}</p>
        ) : alerts && alerts.length === 0 && !loading ? (
          <p className="flex items-center justify-center gap-2 py-6 text-[14px] font-medium text-slate-700">
            <CheckCircle2Icon className="h-6 w-6 text-ok" aria-hidden="true" />
            {t('alerts_none')}
          </p>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-white">
            {(alerts ?? []).map((a) => {
              const ui = alertUi(a.alert_level);
              const Icon = ui?.icon ?? BellIcon;
              const tone = TONE_CLASS[ui?.tone ?? 'muted'];
              return (
                <li key={a.station_id} className="flex flex-wrap items-center gap-4 px-4 py-3">
                  <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border ${tone.box}`}>
                    <Icon className={`h-7 w-7 ${tone.icon}`} aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1 basis-[280px]">
                    <p className="text-[14.5px] font-bold text-ink">
                      {ui ? t(ui.labelKey) : a.alert_level} · {a.station_name}
                    </p>
                    <p className="text-[13px] leading-snug text-slate-700">{a.recommendation}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-[12px] text-slate-600">{t('hero_reserve')}</p>
                    <p className="text-[17px] font-bold tabular-nums text-ink">
                      {Math.round(a.delta_p_needed_kw).toLocaleString()} <span className="text-[12.5px] font-medium text-slate-600">kW</span>
                    </p>
                    <p className="text-[11.5px] tabular-nums text-muted">{forecastTimeLabel(a.timestamp, 0)}</p>
                  </div>
                  <button
                    onClick={() => setSelectedStationId(a.station_id)}
                    className="shrink-0 rounded-lg border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-brand hover:bg-brand-soft"
                  >
                    {t('select_station')}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <StationTable />
    </div>
  );
}
