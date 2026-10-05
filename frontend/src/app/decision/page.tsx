"use client";

import React, { useEffect, useState } from 'react';
import { HistoryIcon, LightbulbIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { DecisionSupport } from '@/components/UI/DecisionSupport';
import { StatusHero } from '@/components/UI/StatusHero';
import { Panel } from '@/components/UI/Panel';
import { useForecast } from '@/context/ForecastContext';
import { PredictionResultData, solarApi } from '@/services/api';
import { CLOUD_UI, TONE_CLASS, alertUi } from '@/lib/levels';
import { forecastTimeLabel } from '@/lib/time';

export default function DecisionPage() {
  const t = useTranslations('common');
  const { selectedStationId, lastUpdated } = useForecast();
  const [history, setHistory] = useState<PredictionResultData[]>([]);

  // Past decisions of this station, as produced by the model every 10 minutes
  useEffect(() => {
    if (!selectedStationId) return;
    let cancelled = false;
    solarApi.getPredictionHistory(selectedStationId, 24).then((rows) => {
      if (!cancelled) setHistory(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedStationId, lastUpdated]);

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
          <LightbulbIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('decision_page_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('decision_page_desc')}</p>
        </div>
      </div>

      <StatusHero />
      <DecisionSupport />

      <Panel title={t('decision_history_title')} icon={<HistoryIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        {history.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-muted">{t('no_data')}</p>
        ) : (
          <div className="max-h-[320px] overflow-auto rounded-lg border border-line">
            <table className="w-full text-left text-[13px]">
              <thead className="sticky top-0 border-b border-line bg-canvas font-bold text-slate-700">
                <tr>
                  <th className="px-3 py-2">{t('th_time')}</th>
                  <th className="px-3 py-2">{t('th_alert')}</th>
                  <th className="px-3 py-2">{t('cloud_cover')}</th>
                  <th className="px-3 py-2 text-right">{t('kpi_dp')}</th>
                  <th className="px-3 py-2 text-right">{t('hero_reserve')}</th>
                  <th className="px-3 py-2">{t('recommendation')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white">
                {history.map((h) => {
                  const ui = alertUi(h.alert_level);
                  const Icon = ui?.icon;
                  const cloud = h.cloud_impact_level ? CLOUD_UI[h.cloud_impact_level] : null;
                  return (
                    <tr key={h.job_id}>
                      <td className="whitespace-nowrap px-3 py-2 font-medium tabular-nums text-ink">
                        {forecastTimeLabel(h.data_time || h.predicted_at, 0)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-semibold ${TONE_CLASS[ui?.tone ?? 'muted'].chip}`}>
                          {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
                          {ui ? t(ui.labelKey) : h.alert_level}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-700">
                        {cloud && h.cloud_coverage_now_pct !== null && h.cloud_coverage_now_pct !== undefined
                          ? `${Math.round(h.cloud_coverage_now_pct)}% · ${t(cloud.labelKey)}`
                          : '—'}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-700">{Math.round(h.delta_p_kw).toLocaleString()}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                        {h.reserve_kw === null || h.reserve_kw === undefined ? '—' : Math.round(h.reserve_kw).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{h.recommendation_text}</td>
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
