"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { LineChartIcon, TableIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { CloudPlayer } from '@/components/UI/CloudPlayer';
import { DayCloudChart, DayGhiChart, DayPowerChart, DayRow } from '@/components/UI/DayCharts';
import { ForecastFreshness } from '@/components/UI/ForecastFreshness';
import { Panel } from '@/components/UI/Panel';
import { useForecast } from '@/context/ForecastContext';
import { CLOUD_UI, impactLevelOfLoss } from '@/lib/levels';
import { parseBackendDate } from '@/lib/time';
import { DayFramesResponse, DayViewResponse, LEAD_OPTIONS, LeadMinutes, dayViewApi, thaiDayMs, todayThai } from '@/services/dayViewApi';

const STEP_MS = 600_000;
// Hours shown on the day charts (Thailand time): from before sunrise to after sunset
const DAY_START: [number, number] = [5, 30];
const DAY_END: [number, number] = [19, 0];

export default function ForecastPage() {
  const t = useTranslations('common');
  const { chartGhiData, chartPowerData, prediction, selectedStationId, selectedStation } = useForecast();

  const [date, setDate] = useState(todayThai());
  const [lead, setLead] = useState<LeadMinutes>(10);
  const [view, setView] = useState<DayViewResponse | null>(null);
  const [frames, setFrames] = useState<DayFramesResponse | null>(null);
  const [loadingFrames, setLoadingFrames] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isToday = date === todayThai();
  // a new forecast round (today only) is the signal to read the day again
  const roundKey = isToday ? prediction?.predicted_at ?? '' : '';

  const viewSeq = useRef(0);
  useEffect(() => {
    if (!selectedStationId) return;
    const seq = ++viewSeq.current;
    dayViewApi
      .getDayView(selectedStationId, date, lead)
      .then((d) => {
        if (seq === viewSeq.current) {
          setView(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (seq === viewSeq.current) {
          setView(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
  }, [selectedStationId, date, lead, roundKey]);

  const frameSeq = useRef(0);
  useEffect(() => {
    if (!selectedStationId) return;
    const seq = ++frameSeq.current;
    setLoadingFrames(true);
    dayViewApi
      .getDayFrames(selectedStationId, date)
      .then((d) => {
        if (seq === frameSeq.current) setFrames(d);
      })
      .catch(() => {
        if (seq === frameSeq.current) setFrames(null);
      })
      .finally(() => {
        if (seq === frameSeq.current) setLoadingFrames(false);
      });
  }, [selectedStationId, date, roundKey]);

  // another station or day: do not keep showing the previous one while the new data loads
  useEffect(() => {
    setView(null);
    setFrames(null);
  }, [selectedStationId, date]);

  const startMs = thaiDayMs(date, ...DAY_START);
  const endMs = thaiDayMs(date, ...DAY_END);
  const nowMs = isToday ? Date.now() : null;

  const rows = useMemo<DayRow[]>(() => {
    if (!view) return [];
    const kwPerWm2 = selectedStation ? (selectedStation.panel_area * selectedStation.efficiency) / 1000 : null;

    // typical error range of the newest forecast, per slot (today only)
    const bandBy = new Map<number, [number, number]>();
    const base = isToday && prediction ? parseBackendDate(prediction.data_time || prediction.predicted_at) : null;
    if (base && prediction) {
      const origin = Math.floor((base.getTime() + STEP_MS / 2) / STEP_MS) * STEP_MS; // same rounding as the worker
      prediction.ghi_forecast_curve.forEach((_, i) => {
        const lo = prediction.ghi_forecast_lower?.[i];
        const hi = prediction.ghi_forecast_upper?.[i];
        if (lo !== undefined && lo !== null && hi !== undefined && hi !== null) bandBy.set(origin + (i + 1) * STEP_MS, [lo, hi]);
      });
    }
    const cloudBy = new Map<number, number | null>((frames?.frames ?? []).map((f) => [Date.parse(f.timestamp), f.cloud_pct]));
    const toKw = (ghi: number | null) => (ghi === null || kwPerWm2 === null ? null : Math.round(ghi * kwPerWm2));

    return view.points
      .map((p) => ({ p, ms: parseBackendDate(p.timestamp)?.getTime() ?? NaN }))
      .filter(({ ms }) => ms >= startMs && ms <= endMs)
      .map(({ p, ms }) => {
        const band = bandBy.get(ms) ?? null;
        return {
          ms,
          forecast: p.forecast_ghi === null ? null : Math.round(p.forecast_ghi),
          lstm: p.forecast_ghi_lstm === null ? null : Math.round(p.forecast_ghi_lstm),
          lead: p.forecast_lead_minutes,
          weather: p.weather_ghi === null ? null : Math.round(p.weather_ghi),
          label: p.label_ghi === null ? null : Math.round(p.label_ghi),
          clearsky: p.clearsky_ghi === null ? null : Math.round(p.clearsky_ghi),
          band: band ? ([Math.round(band[0]), Math.round(band[1])] as [number, number]) : null,
          gen: toKw(p.forecast_ghi),
          genBand: band && kwPerWm2 !== null ? ([Math.round(band[0] * kwPerWm2), Math.round(band[1] * kwPerWm2)] as [number, number]) : null,
          labelKw: toKw(p.label_ghi),
          target: p.forecast_target_kw === null ? null : Math.round(p.forecast_target_kw),
          cloudObserved: cloudBy.get(ms) ?? null,
          cloudForecast: p.forecast_cloud_pct,
          lossForecast: p.forecast_sat_loss_pct,
        };
      });
  }, [view, frames, prediction, selectedStation, isToday, startMs, endMs]);

  const chartProps = { rows, startMs, endMs, nowMs, leadMinutes: lead };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sun/15 text-sun">
          <LineChartIcon className="h-6 w-6 text-sun" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('forecast_page_title')}</h1>
          <p className="text-[13.5px] text-slate-600">
            {t('dv_page_desc')}
            {prediction?.model_version ? ` · ${t('model_version')} ${prediction.model_version}` : ''}
          </p>
        </div>
        <ForecastFreshness />
      </div>

      {/* what the day charts show: which day, and how far ahead the past forecasts were made */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-line bg-white px-3.5 py-2.5 text-[13px] text-slate-700">
        <label className="flex items-center gap-2">
          <span className="font-semibold text-ink">{t('lb_date')}</span>
          <input
            type="date"
            value={date}
            max={todayThai()}
            onChange={(e) => e.target.value && setDate(e.target.value)}
            className="h-9 rounded-lg border border-line bg-white px-2 text-[13px] text-ink"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t('dv_lead_label')}>
          <span className="font-semibold text-ink">{t('dv_lead_label')}</span>
          {LEAD_OPTIONS.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={lead === m}
              onClick={() => setLead(m)}
              className={`h-9 rounded-lg border px-3 font-semibold tabular-nums ${
                lead === m ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-white text-slate-700 hover:bg-canvas'
              }`}
            >
              {t('dv_lead_option', { minutes: m })}
            </button>
          ))}
        </div>
        <p className="min-w-[240px] flex-1 text-[12.5px] leading-snug text-slate-600">
          {view && view.view_mae_vs_label !== null && view.view_mae_lstm_vs_label !== null
            ? t('dv_mae_line', {
                lead,
                blend: view.view_mae_vs_label.toFixed(0),
                lstm: view.view_mae_lstm_vs_label.toFixed(0),
                n: view.view_matched_label_count,
              })
            : t('dv_mae_none')}
        </p>
      </div>

      {error && (
        <p role="alert" className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {t('lb_error')}: {error}
        </p>
      )}

      <div className="h-[330px] shrink-0">
        <DayGhiChart {...chartProps} />
      </div>
      <div className="h-[290px] shrink-0">
        <DayPowerChart {...chartProps} />
      </div>
      <div className="grid shrink-0 grid-cols-1 gap-3.5 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.8fr)] [&>*]:h-[400px]">
        <DayCloudChart {...chartProps} />
        <CloudPlayer data={frames} loading={loadingFrames} />
      </div>

      {/* The newest 3-hour forecast as numbers, for reading exact values */}
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
