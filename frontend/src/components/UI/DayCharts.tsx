"use client";

import React from 'react';
import { CloudIcon, SunIcon, ZapIcon } from 'lucide-react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { hhmmThai } from '@/services/dayViewApi';

/** One 10-minute slot of the day, already converted for the three charts. */
export type DayRow = {
  ms: number;
  /** past: forecast made `lead` minutes earlier; future: the newest forecast */
  forecast: number | null;
  lstm: number | null;
  lead: number | null;
  weather: number | null;
  label: number | null;
  clearsky: number | null;
  band: [number, number] | null;
  gen: number | null;
  genBand: [number, number] | null;
  labelKw: number | null;
  target: number | null;
  cloudObserved: number | null;
  cloudForecast: number | null;
  lossForecast: number | null;
};

export type DayChartProps = {
  rows: DayRow[];
  startMs: number;
  endMs: number;
  /** null when the day on screen is not today */
  nowMs: number | null;
  leadMinutes: number;
};

// Colours checked with the dataviz palette validator on the white surface (adjacent pairs separate for
// colour-blind readers). The forecast is the answer (accent), the LSTM line is context (grey, dashed),
// measured values are dots so they never depend on colour alone.
const FORECAST = '#1d4ed8';
const LSTM = '#64748b';
const WEATHER = '#7c3aed';
const MEASURED = '#16a34a';
const CLEARSKY = '#cbd5e1';
const OBSERVED_CLOUD = '#94a3b8';

const AXIS_TICK = { fontSize: 11, fill: '#475569' };

function hourTicks(startMs: number, endMs: number): number[] {
  const hour = 3600_000;
  const ticks = [];
  for (let t = Math.ceil(startMs / hour) * hour; t <= endMs; t += hour) ticks.push(t);
  return ticks;
}

function Swatch({ kind, color }: { kind: 'line' | 'dash' | 'dot' | 'band' | 'area'; color: string }) {
  if (kind === 'dot') return <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />;
  if (kind === 'band') return <span className="h-2.5 w-5 rounded-sm" style={{ background: color, opacity: 0.18 }} />;
  if (kind === 'area') return <span className="h-2.5 w-5 rounded-sm" style={{ background: color, opacity: 0.45 }} />;
  if (kind === 'dash') return <span className="w-5 border-t-2 border-dashed" style={{ borderColor: color }} />;
  return <span className="h-0.5 w-5" style={{ background: color }} />;
}

function Legend({ items }: { items: { kind: 'line' | 'dash' | 'dot' | 'band' | 'area'; color: string; label: string }[] }) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-0.5 text-[12px] text-slate-700">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5 whitespace-nowrap">
          <Swatch kind={it.kind} color={it.color} /> {it.label}
        </span>
      ))}
    </div>
  );
}

type TipRow = { kind: 'line' | 'dash' | 'dot' | 'band' | 'area'; color: string; label: string; value: string | null };

function TipBox({ title, note, rows }: { title: string; note?: string | null; rows: TipRow[] }) {
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-[12.5px] text-slate-700 shadow-lg">
      <p className="mb-1 font-bold text-ink">{title}</p>
      {rows
        .filter((r) => r.value !== null)
        .map((r) => (
          <p key={r.label} className="flex items-center gap-2">
            <Swatch kind={r.kind} color={r.color} />
            {r.label}: <b className="tabular-nums text-ink">{r.value}</b>
          </p>
        ))}
      {note && <p className="mt-1 text-muted">{note}</p>}
    </div>
  );
}

const num = (v: number | null | undefined, unit: string) => (v === null || v === undefined ? null : `${Math.round(v).toLocaleString()} ${unit}`);

type TipProps = { active?: boolean; payload?: { payload: DayRow }[] };

/** Shared frame of the three charts: hourly time axis, "now" marker and a tint over the hours still ahead. */
function DayFrame({
  rows,
  startMs,
  endMs,
  nowMs,
  yMax,
  yTickFormatter,
  tooltip,
  futureLabel,
  children,
}: DayChartProps & {
  yMax: number;
  yTickFormatter?: (v: number) => string;
  tooltip: React.ReactElement;
  futureLabel: string;
  children: React.ReactNode;
}) {
  const showNow = nowMs !== null && nowMs > startMs && nowMs < endMs;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 14, right: 12, left: -8, bottom: -4 }}>
        <CartesianGrid stroke="#eef2f7" vertical={false} />
        <XAxis
          dataKey="ms"
          type="number"
          domain={[startMs, endMs]}
          ticks={hourTicks(startMs, endMs)}
          tickFormatter={(v: number) => hhmmThai(v)}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={{ stroke: '#cbd5e1' }}
        />
        <YAxis domain={[0, yMax]} tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={yTickFormatter} />
        {showNow && <ReferenceArea x1={nowMs as number} x2={endMs} fill="#eaf1ff" fillOpacity={0.55} strokeOpacity={0} />}
        {showNow && (
          <ReferenceLine
            x={nowMs as number}
            stroke="#0f172a"
            strokeDasharray="3 3"
            label={{ value: futureLabel, position: 'insideTopLeft', fontSize: 11, fill: '#334155', dx: 4, dy: -12 }}
          />
        )}
        <Tooltip content={tooltip} cursor={{ stroke: '#94a3b8', strokeWidth: 1 }} />
        {children}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="flex flex-1 items-center justify-center text-[13px] text-muted">{text}</p>;
}

export function DayGhiChart(props: DayChartProps) {
  const t = useTranslations('common');
  const { rows, nowMs, leadMinutes } = props;
  const has = (k: keyof DayRow) => rows.some((r) => r[k] !== null);
  const yMax = Math.max(200, Math.ceil(Math.max(...rows.map((r) => Math.max(r.forecast ?? 0, r.lstm ?? 0, r.weather ?? 0, r.label ?? 0, r.clearsky ?? 0, r.band?.[1] ?? 0)), 0) / 200) * 200);

  function Tip({ active, payload }: TipProps) {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    const ahead = nowMs !== null && p.ms > nowMs;
    return (
      <TipBox
        title={hhmmThai(p.ms)}
        note={p.forecast === null ? null : ahead ? t('dv_tip_latest', { lead: p.lead ?? 0 }) : t('dv_tip_lead', { lead: p.lead ?? leadMinutes })}
        rows={[
          { kind: 'dot', color: MEASURED, label: t('dv_measured'), value: num(p.label, 'W/m²') },
          { kind: 'line', color: FORECAST, label: t('ghi_blend'), value: num(p.forecast, 'W/m²') },
          { kind: 'dash', color: LSTM, label: t('ghi_lstm'), value: num(p.lstm, 'W/m²') },
          { kind: 'band', color: FORECAST, label: t('band_legend'), value: p.band ? `${p.band[0]}–${p.band[1]} W/m²` : null },
          { kind: 'line', color: WEATHER, label: t('dv_weather'), value: num(p.weather, 'W/m²') },
          { kind: 'line', color: CLEARSKY, label: t('dv_clearsky'), value: num(p.clearsky, 'W/m²') },
        ]}
      />
    );
  }

  return (
    <Panel
      title={t('dv_ghi_title')}
      icon={<SunIcon className="h-5 w-5 text-sun" />}
      className="h-full"
      action={
        <div className="flex items-center gap-2">
          <Legend
            items={[
              { kind: 'line', color: FORECAST, label: t('ghi_blend') },
              { kind: 'dash', color: LSTM, label: t('ghi_lstm') },
              { kind: 'line', color: WEATHER, label: t('dv_weather') },
              ...(has('label') ? [{ kind: 'dot' as const, color: MEASURED, label: t('dv_measured') }] : []),
              { kind: 'line', color: CLEARSKY, label: t('dv_clearsky') },
              ...(has('band') ? [{ kind: 'band' as const, color: FORECAST, label: t('band_legend') }] : []),
            ]}
          />
          <InfoTip text={t('dv_ghi_help')} align="right" />
        </div>
      }
    >
      {rows.length === 0 ? (
        <Empty text={t('dv_no_data')} />
      ) : (
        <div className="min-h-0 flex-1">
          <DayFrame {...props} yMax={yMax} tooltip={<Tip />} futureLabel={t('dv_ahead')}>
            <Line dataKey="clearsky" stroke={CLEARSKY} strokeWidth={1.5} dot={false} activeDot={false} isAnimationActive={false} connectNulls />
            <Area dataKey="band" stroke="none" fill={FORECAST} fillOpacity={0.14} activeDot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="weather" stroke={WEATHER} strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            <Line dataKey="lstm" stroke={LSTM} strokeWidth={2} strokeDasharray="6 5" dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            <Line dataKey="forecast" stroke={FORECAST} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            <Scatter dataKey="label" fill={MEASURED} stroke="#ffffff" strokeWidth={1} isAnimationActive={false} />
          </DayFrame>
        </div>
      )}
    </Panel>
  );
}

export function DayPowerChart(props: DayChartProps) {
  const t = useTranslations('common');
  const { rows, nowMs, leadMinutes } = props;
  const has = (k: keyof DayRow) => rows.some((r) => r[k] !== null);
  const top = Math.max(...rows.map((r) => Math.max(r.gen ?? 0, r.target ?? 0, r.labelKw ?? 0, r.genBand?.[1] ?? 0)), 0);
  const stepKw = top > 4000 ? 1000 : top > 1500 ? 500 : 250;
  const yMax = Math.max(stepKw, Math.ceil(top / stepKw) * stepKw);

  function Tip({ active, payload }: TipProps) {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    const ahead = nowMs !== null && p.ms > nowMs;
    return (
      <TipBox
        title={hhmmThai(p.ms)}
        note={p.gen === null ? null : ahead ? t('dv_tip_latest', { lead: p.lead ?? 0 }) : t('dv_tip_lead', { lead: p.lead ?? leadMinutes })}
        rows={[
          { kind: 'dot', color: MEASURED, label: t('dv_power_measured'), value: num(p.labelKw, 'kW') },
          { kind: 'line', color: FORECAST, label: t('dv_power_forecast'), value: num(p.gen, 'kW') },
          { kind: 'band', color: FORECAST, label: t('band_legend'), value: p.genBand ? `${p.genBand[0].toLocaleString()}–${p.genBand[1].toLocaleString()} kW` : null },
          { kind: 'dash', color: LSTM, label: t('dv_target'), value: num(p.target, 'kW') },
        ]}
      />
    );
  }

  return (
    <Panel
      title={t('dv_power_title')}
      icon={<ZapIcon className="h-5 w-5 text-brand" />}
      className="h-full"
      action={
        <div className="flex items-center gap-2">
          <Legend
            items={[
              { kind: 'line', color: FORECAST, label: t('dv_power_forecast') },
              { kind: 'dash', color: LSTM, label: t('dv_target') },
              ...(has('labelKw') ? [{ kind: 'dot' as const, color: MEASURED, label: t('dv_power_measured') }] : []),
              ...(has('genBand') ? [{ kind: 'band' as const, color: FORECAST, label: t('band_legend') }] : []),
            ]}
          />
          <InfoTip text={t('dv_power_help')} align="right" />
        </div>
      }
    >
      {rows.length === 0 ? (
        <Empty text={t('dv_no_data')} />
      ) : (
        <div className="min-h-0 flex-1">
          <DayFrame {...props} yMax={yMax} yTickFormatter={(v) => v.toLocaleString()} tooltip={<Tip />} futureLabel={t('dv_ahead')}>
            <Area dataKey="genBand" stroke="none" fill={FORECAST} fillOpacity={0.14} activeDot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="target" stroke={LSTM} strokeWidth={2} strokeDasharray="6 5" dot={false} activeDot={false} isAnimationActive={false} />
            <Line dataKey="gen" stroke={FORECAST} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
            <Scatter dataKey="labelKw" fill={MEASURED} stroke="#ffffff" strokeWidth={1} isAnimationActive={false} />
          </DayFrame>
        </div>
      )}
    </Panel>
  );
}

export function DayCloudChart(props: DayChartProps) {
  const t = useTranslations('common');
  const { rows, nowMs, leadMinutes } = props;
  const any = rows.some((r) => r.cloudObserved !== null || r.cloudForecast !== null || r.lossForecast !== null);
  const pct = (v: number | null) => (v === null ? null : `${Math.round(v)}%`);

  function Tip({ active, payload }: TipProps) {
    if (!active || !payload?.length) return null;
    const p = payload[0].payload;
    const ahead = nowMs !== null && p.ms > nowMs;
    return (
      <TipBox
        title={hhmmThai(p.ms)}
        note={p.cloudForecast === null && p.lossForecast === null ? null : ahead ? t('dv_tip_latest', { lead: p.lead ?? 0 }) : t('dv_tip_lead', { lead: p.lead ?? leadMinutes })}
        rows={[
          { kind: 'area', color: OBSERVED_CLOUD, label: t('dv_cloud_observed'), value: pct(p.cloudObserved) },
          { kind: 'line', color: FORECAST, label: t('dv_cloud_forecast'), value: pct(p.cloudForecast) },
          { kind: 'dash', color: WEATHER, label: t('dv_loss_forecast'), value: pct(p.lossForecast) },
        ]}
      />
    );
  }

  return (
    <Panel
      title={t('dv_cloud_title')}
      icon={<CloudIcon className="h-5 w-5 text-slate-600" />}
      className="h-full"
      action={
        <div className="flex items-center gap-2">
          <Legend
            items={[
              { kind: 'area', color: OBSERVED_CLOUD, label: t('dv_cloud_observed') },
              { kind: 'line', color: FORECAST, label: t('dv_cloud_forecast') },
              { kind: 'dash', color: WEATHER, label: t('dv_loss_forecast') },
            ]}
          />
          <InfoTip text={t('dv_cloud_help')} align="right" />
        </div>
      }
    >
      {!any ? (
        <Empty text={t('dv_no_cloud')} />
      ) : (
        <div className="min-h-0 flex-1">
          <DayFrame {...props} yMax={100} yTickFormatter={(v) => `${v}%`} tooltip={<Tip />} futureLabel={t('dv_ahead')}>
            <Area dataKey="cloudObserved" type="stepAfter" stroke={OBSERVED_CLOUD} strokeWidth={1} fill={OBSERVED_CLOUD} fillOpacity={0.35} activeDot={false} isAnimationActive={false} />
            <Line dataKey="lossForecast" stroke={WEATHER} strokeWidth={2} strokeDasharray="6 5" dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
            <Line dataKey="cloudForecast" stroke={FORECAST} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          </DayFrame>
        </div>
      )}
    </Panel>
  );
}
