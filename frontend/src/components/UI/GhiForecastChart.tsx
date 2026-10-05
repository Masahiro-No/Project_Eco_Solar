"use client";

import React from 'react';
import { SunIcon } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { GhiChartPoint, useForecast } from '@/context/ForecastContext';

// Series colours come from the theme (app/globals.css); both sets were checked with the dataviz palette validator.
// The blended forecast is the answer (accent); the LSTM line is context (de-emphasised, dashed).
const BLEND = 'var(--chart-forecast)';
const LSTM = 'var(--chart-context)';

type TipProps = { active?: boolean; payload?: { payload: GhiChartPoint }[] };

function GhiTooltip({ active, payload, labels }: TipProps & { labels: Record<string, string> }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-[12.5px] text-slate-700 shadow-lg">
      <p className="mb-1 font-bold text-ink">{p.t}</p>
      <p className="flex items-center gap-2">
        <span className="h-0.5 w-4" style={{ background: BLEND }} />
        {labels.blend}: <b className="tabular-nums text-ink">{p.blend}</b> W/m²
      </p>
      {p.lstm !== null && (
        <p className="flex items-center gap-2">
          <span className="w-4 border-t-2 border-dashed" style={{ borderColor: LSTM }} />
          {labels.lstm}: <b className="tabular-nums text-ink">{p.lstm}</b> W/m²
        </p>
      )}
      {p.band && (
        <p className="flex items-center gap-2">
          <span className="h-2.5 w-4 rounded-sm" style={{ background: BLEND, opacity: 0.18 }} />
          {labels.band}: <b className="tabular-nums text-ink">{p.band[0]}–{p.band[1]}</b> W/m²
        </p>
      )}
      <p className="mt-1 text-muted">
        {labels.weight}: {p.weightPct === null ? '—' : `${p.weightPct}%`} · {labels.cloud}: {p.cloudPct === null ? '—' : `${p.cloudPct}%`}
      </p>
    </div>
  );
}

export function GhiForecastChart() {
  const t = useTranslations('common');
  const { chartGhiData, prediction } = useForecast();

  const hasSatellite = chartGhiData.some((p) => (p.weightPct ?? 0) > 0);
  const firstWeight = chartGhiData.find((p) => p.weightPct !== null)?.weightPct ?? 0;
  const hasBand = chartGhiData.some((p) => p.band !== null);
  const yMax = Math.max(200, Math.ceil(Math.max(...chartGhiData.map((p) => Math.max(p.blend, p.lstm ?? 0, p.band?.[1] ?? 0)), 0) / 200) * 200);
  const labels = { blend: t('ghi_blend'), lstm: t('ghi_lstm'), weight: t('ghi_weight'), cloud: t('cloud_cover'), band: t('band_legend') };

  return (
    <Panel
      title={t('ghi_forecast_title')}
      icon={<SunIcon className="h-5 w-5 text-sun" />}
      className="h-full"
      action={
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-0.5 text-[12px] text-slate-700">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-0.5 w-5" style={{ background: BLEND }} /> {t('ghi_blend')}
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="w-5 border-t-2 border-dashed" style={{ borderColor: LSTM }} /> {t('ghi_lstm')}
          </span>
          {hasBand && (
            <span className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="h-2.5 w-5 rounded-sm" style={{ background: BLEND, opacity: 0.18 }} /> {t('band_legend')}
            </span>
          )}
          <InfoTip text={`${t('help_ghi_blend')} ${t('help_band')}`} align="right" />
        </div>
      }
    >
      {chartGhiData.length === 0 ? (
        <p className="flex flex-1 items-center justify-center text-[13px] text-muted">{t('no_forecast_title')}</p>
      ) : (
        <>
          <p className="shrink-0 text-[11.5px] text-slate-600">
            {t('ghi_unit')} ·{' '}
            {prediction?.is_night
              ? t('ghi_note_night')
              : hasSatellite
              ? t('ghi_note_blend', { pct: firstWeight })
              : t('ghi_note_lstm_only')}
          </p>
          <div className="min-h-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartGhiData} margin={{ top: 8, right: 10, left: -14, bottom: -4 }}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: 'var(--chart-tick)' }} tickLine={false} axisLine={{ stroke: 'var(--chart-axis)' }} interval={2} />
                <YAxis domain={[0, yMax]} tick={{ fontSize: 11, fill: 'var(--chart-tick)' }} tickLine={false} axisLine={false} />
                <Tooltip content={<GhiTooltip labels={labels} />} cursor={{ stroke: 'var(--chart-cursor)', strokeWidth: 1 }} />
                <Area dataKey="band" stroke="none" fill={BLEND} fillOpacity={0.14} activeDot={false} isAnimationActive={false} connectNulls />
                <Line dataKey="lstm" stroke={LSTM} strokeWidth={2} strokeDasharray="6 5" dot={false} activeDot={{ r: 4 }} isAnimationActive={false} connectNulls />
                <Line dataKey="blend" stroke={BLEND} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
}
