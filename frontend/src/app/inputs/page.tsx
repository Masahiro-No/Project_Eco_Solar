"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DatabaseIcon, SatelliteIcon, ThermometerIcon } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { useForecast } from '@/context/ForecastContext';
import { isSatelliteStatus } from '@/lib/levels';
import { parseBackendDate } from '@/lib/time';
import { DayFramesResponse, WeatherRow, dayViewApi, hhmmThai, thaiDayMs, todayThai } from '@/services/dayViewApi';

const STEP_MS = 600_000;
const WINDOW_FRAMES = 12; // frames the ConvLSTM reads
const AXIS_TICK = { fontSize: 11, fill: 'var(--chart-tick)' };

type Row = WeatherRow & { ms: number; ratio: number | null };
type Series = { key: keyof Row; label: string; color: string; dash?: boolean };

function MiniChart({ title, unit, series, rows, startMs, endMs, digits = 0 }: {
  title: string;
  unit: string;
  series: Series[];
  rows: Row[];
  startMs: number;
  endMs: number;
  digits?: number;
}) {
  const last = rows.length ? rows[rows.length - 1] : null;
  const shown = series.filter((s) => rows.some((r) => r[s.key] !== null && r[s.key] !== undefined));
  const ticks = [];
  for (let t = startMs; t <= endMs; t += 3 * 3600_000) ticks.push(t);
  const fmt = (v: unknown) => (typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—');

  return (
    <section className="flex h-[230px] flex-col rounded-xl border border-line bg-white p-3">
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-[14px] font-bold text-ink">
          {title} <span className="font-normal text-slate-600">({unit})</span>
        </h3>
        <p className="text-[12.5px] tabular-nums text-slate-700">
          {shown.map((s, i) => (
            <span key={String(s.key)} className="ml-2 whitespace-nowrap first:ml-0">
              {shown.length > 1 && (
                <span className="mr-1 inline-block w-4 border-t-2 align-middle" style={{ borderColor: s.color, borderStyle: s.dash ? 'dashed' : 'solid' }} />
              )}
              {shown.length > 1 ? `${s.label} ` : ''}
              <b className="text-ink">{last ? fmt(last[s.key]) : '—'}</b>
              {i === shown.length - 1 ? '' : ' ·'}
            </span>
          ))}
        </p>
      </header>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 10, left: -12, bottom: -4 }}>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis dataKey="ms" type="number" domain={[startMs, endMs]} ticks={ticks} tickFormatter={(v: number) => hhmmThai(v)} tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: 'var(--chart-axis)' }} />
            <YAxis domain={['auto', 'auto']} tick={AXIS_TICK} tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 })} />
            <Tooltip
              labelFormatter={(v) => hhmmThai(Number(v))}
              formatter={(value, name) => [`${fmt(value)} ${unit}`, name]}
              contentStyle={{ fontSize: 12.5, borderRadius: 8, borderColor: 'var(--chart-axis)', background: 'var(--chart-tooltip-bg)', color: 'var(--chart-tooltip-ink)' }}
            />
            {shown.map((s) => (
              <Line key={String(s.key)} dataKey={s.key as string} name={s.label} stroke={s.color} strokeWidth={2} strokeDasharray={s.dash ? '6 5' : undefined} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

/** What the two models are fed: today's weather values (LSTM) and the newest real frames (ConvLSTM). */
export default function ModelInputsPage() {
  const t = useTranslations('common');
  const { selectedStationId, selectedStation, prediction } = useForecast();
  const [weather, setWeather] = useState<WeatherRow[] | null>(null);
  const [frames, setFrames] = useState<DayFramesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const date = todayThai();
  const roundKey = prediction?.predicted_at ?? '';

  const seq = useRef(0);
  useEffect(() => {
    if (!selectedStationId) return;
    const mine = ++seq.current;
    setError(null);
    dayViewApi
      .getRecentWeather(selectedStationId, 30)
      .then((d) => {
        if (mine === seq.current) setWeather(d);
      })
      .catch((e) => {
        if (mine === seq.current) {
          setWeather(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    dayViewApi
      .getDayFrames(selectedStationId, date)
      .then((d) => {
        if (mine === seq.current) setFrames(d);
      })
      .catch(() => {
        if (mine === seq.current) setFrames(null);
      });
  }, [selectedStationId, date, roundKey]);

  useEffect(() => {
    setWeather(null);
    setFrames(null);
  }, [selectedStationId]);

  const startMs = thaiDayMs(date, 0);
  const endMs = thaiDayMs(date, 24);
  const rows = useMemo<Row[]>(
    () =>
      (weather ?? [])
        .map((w) => ({ ...w, ms: parseBackendDate(w.timestamp)?.getTime() ?? NaN, ratio: w.clearsky_ghi >= 10 ? Math.min(1, Math.max(0, w.ghi) / w.clearsky_ghi) : 0 }))
        .filter((w) => w.ms >= startMs && w.ms < endMs)
        .sort((a, b) => a.ms - b.ms),
    [weather, startMs, endMs],
  );
  const last = rows.length ? rows[rows.length - 1] : null;

  // the 12 scan times the ConvLSTM would read, ending at the newest real frame
  const windowSlots = useMemo(() => {
    const real = frames?.frames ?? [];
    if (real.length === 0) return [];
    const byMs = new Map(real.map((f) => [Date.parse(f.timestamp), f]));
    const end = Date.parse(real[real.length - 1].timestamp);
    return Array.from({ length: WINDOW_FRAMES }, (_, i) => {
      const ms = end - (WINDOW_FRAMES - 1 - i) * STEP_MS;
      return { ms, frame: byMs.get(ms) ?? null };
    });
  }, [frames]);
  const missing = windowSlots.filter((s) => !s.frame).length;

  const features: { name: string; value: string; note: string }[] = last
    ? [
        { name: 'ghi', value: `${last.ghi.toFixed(1)} W/m²`, note: t('in_src_openmeteo') },
        { name: 'dni', value: `${last.dni.toFixed(1)} W/m²`, note: t('in_src_openmeteo') },
        { name: 'dhi', value: last.dhi === null ? '—' : `${last.dhi.toFixed(1)} W/m²`, note: last.dhi === null ? t('in_dhi_missing') : t('in_src_dhi') },
        { name: 'clearsky_ghi', value: `${last.clearsky_ghi.toFixed(1)} W/m²`, note: t('in_src_computed_sun') },
        { name: 'solar_zenith_angle', value: `${last.solar_zenith_angle.toFixed(1)}°`, note: t('in_src_computed_sun') },
        { name: 'clearsky_ratio', value: (last.ratio ?? 0).toFixed(2), note: t('in_src_ratio') },
        { name: 'temperature', value: `${last.temperature.toFixed(1)} °C`, note: t('in_src_openmeteo') },
        { name: 'relative_humidity', value: `${last.relative_humidity.toFixed(0)} %`, note: t('in_src_openmeteo') },
        { name: 'surface_pressure', value: last.surface_pressure === null ? '—' : `${last.surface_pressure.toFixed(1)} hPa`, note: last.surface_pressure === null ? t('in_pressure_missing') : t('in_src_openmeteo') },
        { name: 'wind_speed', value: `${last.wind_speed.toFixed(1)} ${t('in_unit_wind')}`, note: t('in_src_openmeteo') },
      ]
    : [];

  const chart = { rows, startMs, endMs };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 pb-4 text-ink">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
          <DatabaseIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('in_title')}</h1>
          <p className="text-[13.5px] text-slate-600">
            {t('in_desc')}
            {selectedStation ? ` · ${selectedStation.id} ${selectedStation.name}` : ''}
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {t('lb_error')}: {error}
        </p>
      )}

      <Panel title={t('in_lstm_title')} icon={<ThermometerIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        <p className="text-[12.5px] leading-snug text-slate-600">{t('in_lstm_how')}</p>
        {weather !== null && rows.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-muted">{t('in_no_weather')}</p>
        ) : (
          <>
            <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              <MiniChart
                title={t('in_chart_irradiance')}
                unit="W/m²"
                {...chart}
                series={[
                  { key: 'ghi', label: 'GHI', color: 'var(--chart-forecast)' },
                  { key: 'dni', label: 'DNI', color: 'var(--chart-weather)' },
                  { key: 'dhi', label: 'DHI', color: 'var(--chart-teal)' },
                  { key: 'clearsky_ghi', label: t('dv_clearsky'), color: 'var(--chart-observed)', dash: true },
                ]}
              />
              <MiniChart title={t('in_chart_temperature')} unit="°C" digits={1} {...chart} series={[{ key: 'temperature', label: t('in_chart_temperature'), color: 'var(--chart-forecast)' }]} />
              <MiniChart title={t('in_chart_humidity')} unit="%" {...chart} series={[{ key: 'relative_humidity', label: t('in_chart_humidity'), color: 'var(--chart-forecast)' }]} />
              <MiniChart title={t('in_chart_wind')} unit={t('in_unit_wind')} digits={1} {...chart} series={[{ key: 'wind_speed', label: t('in_chart_wind'), color: 'var(--chart-forecast)' }]} />
              <MiniChart title={t('in_chart_pressure')} unit="hPa" digits={1} {...chart} series={[{ key: 'surface_pressure', label: t('in_chart_pressure'), color: 'var(--chart-forecast)' }]} />
              <MiniChart title={t('in_chart_zenith')} unit="°" digits={1} {...chart} series={[{ key: 'solar_zenith_angle', label: t('in_chart_zenith'), color: 'var(--chart-forecast)' }]} />
            </div>

            {last && (
              <>
                <h3 className="mt-4 text-[14px] font-bold text-ink">{t('in_latest_title', { time: hhmmThai(last.ms) })}</h3>
                <div className="mt-2 overflow-x-auto rounded-lg border border-line">
                  <table className="w-full text-left text-[13px]">
                    <thead className="border-b border-line bg-canvas font-bold text-slate-700">
                      <tr>
                        <th className="px-3 py-2">{t('in_col_feature')}</th>
                        <th className="px-3 py-2 text-right">{t('in_col_value')}</th>
                        <th className="px-3 py-2">{t('in_col_source')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line bg-white text-slate-700">
                      {features.map((f) => (
                        <tr key={f.name}>
                          <td className="px-3 py-1.5 font-mono text-[12.5px] text-ink">{f.name}</td>
                          <td className="px-3 py-1.5 text-right font-semibold tabular-nums text-ink">{f.value}</td>
                          <td className="px-3 py-1.5">{f.note}</td>
                        </tr>
                      ))}
                      <tr>
                        <td className="px-3 py-1.5 font-mono text-[12.5px] text-ink">sin/cos × 6</td>
                        <td className="px-3 py-1.5 text-right text-slate-600">—</td>
                        <td className="px-3 py-1.5">{t('in_time_features')}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[12.5px] leading-snug text-slate-600">{t('in_not_used')}</p>
              </>
            )}
          </>
        )}
      </Panel>

      <Panel title={t('in_convlstm_title')} icon={<SatelliteIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        <p className="text-[12.5px] leading-snug text-slate-600">{t('in_convlstm_how')}</p>
        {windowSlots.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-muted">{frames ? t('cp_no_frames') : t('cp_loading')}</p>
        ) : (
          <>
            <p className="mt-2 text-[13px] text-slate-700">
              {missing === 0 ? t('in_window_complete') : t('in_window_incomplete', { n: missing })}
              {prediction?.satellite_status
                ? ` · ${t('in_round_status', { status: isSatelliteStatus(prediction.satellite_status) ? t(`sat_short_${prediction.satellite_status}`) : prediction.satellite_status })}`
                : ''}
            </p>
            <ul className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2">
              {windowSlots.map((s, i) => (
                <li key={s.ms} className="flex flex-col gap-1">
                  <div className={`relative aspect-square w-full overflow-hidden rounded-md ${s.frame ? 'bg-slate-900' : 'border border-dashed border-slate-400 bg-slate-50'}`}>
                    {s.frame ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={`data:image/png;base64,${s.frame.image_b64}`} alt={t('cp_alt_real', { time: hhmmThai(s.ms) })} className="h-full w-full" style={{ imageRendering: 'pixelated' }} />
                    ) : (
                      <span className="flex h-full items-center justify-center px-1 text-center text-[11.5px] font-semibold text-slate-600">{t('in_frame_missing')}</span>
                    )}
                  </div>
                  <p className="text-center text-[12px] tabular-nums text-slate-700">
                    <b className="text-ink">{hhmmThai(s.ms)}</b>
                    <span className="text-slate-500"> · {i + 1}/{WINDOW_FRAMES}</span>
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>
    </div>
  );
}
