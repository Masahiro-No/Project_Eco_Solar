"use client";

import React from 'react';
import { ZapIcon } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { PowerChartPoint, useForecast } from '@/context/ForecastContext';

const GEN = '#1d4ed8';
const TARGET = '#64748b';

type TipProps = { active?: boolean; payload?: { payload: PowerChartPoint }[] };

function PowerTooltip({ active, payload, labels }: TipProps & { labels: Record<string, string> }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const gap = p.target - p.gen;
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-[12.5px] text-slate-700 shadow-lg">
      <p className="mb-1 font-bold text-ink">{p.t}</p>
      <p>
        {labels.gen}: <b className="tabular-nums text-ink">{p.gen.toLocaleString()}</b> kW
      </p>
      <p>
        {labels.target}: <b className="tabular-nums text-ink">{p.target.toLocaleString()}</b> kW
      </p>
      <p className="mt-1 text-muted">
        {gap > 0 ? `${labels.short} ${gap.toLocaleString()} kW` : labels.met}
      </p>
    </div>
  );
}

export function PowerForecastChart() {
  const t = useTranslations('common');
  const { chartPowerData } = useForecast();

  const target = chartPowerData[0]?.target ?? 0;
  const top = Math.max(target, ...chartPowerData.map((p) => p.gen), 0);
  const yMax = Math.max(1000, Math.ceil((top * 1.1) / 1000) * 1000);
  const labels = { gen: t('kpi_pgen'), target: t('kpi_ptarget'), short: t('dp_short'), met: t('dp_met') };

  return (
    <Panel
      title={t('power_forecast_title')}
      icon={<ZapIcon className="h-5 w-5 text-brand" />}
      className="h-full"
      action={
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-0.5 text-[12px] text-slate-700">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="h-0.5 w-5" style={{ background: GEN }} /> {t('kpi_pgen')}
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="w-5 border-t-2 border-dashed" style={{ borderColor: TARGET }} /> {t('kpi_ptarget')}
          </span>
          <InfoTip text={t('help_pgen')} align="right" />
        </div>
      }
    >
      {chartPowerData.length === 0 ? (
        <p className="flex flex-1 items-center justify-center text-[13px] text-muted">{t('no_forecast_title')}</p>
      ) : (
        <>
          <p className="shrink-0 text-[11.5px] text-slate-600">{t('power_unit')}</p>
          <div className="min-h-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartPowerData} margin={{ top: 8, right: 10, left: -4, bottom: -4 }}>
                <CartesianGrid stroke="#eef2f7" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={{ stroke: '#cbd5e1' }} interval={2} />
                <YAxis
                  domain={[0, yMax]}
                  tick={{ fontSize: 11, fill: '#475569' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => v.toLocaleString()}
                />
                <Tooltip content={<PowerTooltip labels={labels} />} cursor={{ stroke: '#94a3b8', strokeWidth: 1 }} />
                <ReferenceLine y={target} stroke={TARGET} strokeWidth={2} strokeDasharray="6 5" />
                <Line dataKey="gen" stroke={GEN} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
}
