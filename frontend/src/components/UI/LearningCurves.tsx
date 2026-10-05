"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { TrendingDownIcon } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { RetrainRun, RunCurves, dayViewApi, thaiDateTime } from '@/services/dayViewApi';

type Model = 'lstm' | 'convlstm';
type CurveKey = 'train_loss' | 'val_mae' | 'mse' | 'ssim' | 'lr';

// which per-epoch values to draw for each model, in reading order: fit to the training data, error on the
// validation data, learning rate
const CHARTS: Record<Model, { key: CurveKey; digits: number }[]> = {
  lstm: [
    { key: 'train_loss', digits: 5 },
    { key: 'val_mae', digits: 1 },
    { key: 'lr', digits: 6 },
  ],
  convlstm: [
    { key: 'train_loss', digits: 4 },
    { key: 'mse', digits: 5 },
    { key: 'ssim', digits: 3 },
    { key: 'lr', digits: 6 },
  ],
};

const AXIS_TICK = { fontSize: 11, fill: 'var(--chart-tick)' };

function EpochChart({ title, points, digits, bestEpoch, bestLabel }: {
  title: string;
  points: { epoch: number; value: number }[];
  digits: number;
  bestEpoch: number | null;
  bestLabel: string;
}) {
  const fmt = (v: number) => (Math.abs(v) < 0.001 && v !== 0 ? v.toExponential(1) : v.toLocaleString(undefined, { maximumFractionDigits: digits }));
  const last = points.length ? points[points.length - 1] : null;
  return (
    <section className="flex h-[210px] flex-col rounded-xl border border-line bg-white p-3">
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3">
        <h3 className="text-[13.5px] font-bold text-ink">{title}</h3>
        <p className="text-[12.5px] tabular-nums text-slate-700">{last ? fmt(last.value) : '—'}</p>
      </header>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 14, right: 12, left: -6, bottom: -4 }}>
            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
            <XAxis dataKey="epoch" type="number" domain={['dataMin', 'dataMax']} allowDecimals={false} tickCount={Math.min(8, points.length)} tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: 'var(--chart-axis)' }} />
            <YAxis domain={['auto', 'auto']} tick={AXIS_TICK} tickLine={false} axisLine={false} width={58} tickFormatter={fmt} />
            <Tooltip
              labelFormatter={(v) => `epoch ${v}`}
              formatter={(value) => [fmt(Number(value)), title]}
              contentStyle={{ fontSize: 12.5, borderRadius: 8, borderColor: 'var(--chart-axis)', background: 'var(--chart-tooltip-bg)', color: 'var(--chart-tooltip-ink)' }}
            />
            {bestEpoch !== null && bestEpoch > 0 && (
              <ReferenceLine x={bestEpoch} stroke="var(--chart-now)" strokeDasharray="3 3" label={{ value: bestLabel, position: 'insideTopRight', fontSize: 11, fill: 'var(--chart-tick)' }} />
            )}
            <Line dataKey="value" stroke="var(--chart-forecast)" strokeWidth={2} dot={{ r: 3, fill: 'var(--chart-forecast)', strokeWidth: 0 }} activeDot={{ r: 5 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

/**
 * Per-epoch learning curves of one retrain run: training loss, error on the validation data and learning rate.
 * This is how to see whether a run converged (the role TensorBoard has in the course).
 */
export function LearningCurves({ model, runs }: { model: Model; runs: RetrainRun[] }) {
  const t = useTranslations('common');
  const withCurves = useMemo(() => runs.filter((r) => r.has_curves), [runs]);
  const [runId, setRunId] = useState<string>('');
  const [data, setData] = useState<RunCurves | null>(null);
  const [error, setError] = useState<string | null>(null);

  // follow the newest run until the user picks another one
  useEffect(() => {
    setRunId((cur) => (cur && withCurves.some((r) => r.run_id === cur) ? cur : withCurves[0]?.run_id ?? ''));
  }, [withCurves]);

  useEffect(() => {
    if (!runId) {
      setData(null);
      return;
    }
    let alive = true;
    dayViewApi
      .getRunCurves(runId)
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) {
          setData(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      alive = false;
    };
  }, [runId]);

  const run = withCurves.find((r) => r.run_id === runId) ?? null;
  const bestEpoch = run && run.details.best_epoch != null ? Number(run.details.best_epoch) : null;
  const charts = CHARTS[model].filter((c) => (data?.curves[c.key]?.length ?? 0) > 0);

  return (
    <Panel
      title={t(model === 'lstm' ? 'lc_title_lstm' : 'lc_title_convlstm')}
      icon={<TrendingDownIcon className="h-5 w-5 text-brand" />}
      className="shrink-0"
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {withCurves.length > 0 && (
            <select
              aria-label={t('lc_pick_run')}
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              className="h-9 rounded-lg border border-line bg-white px-2 text-[13px] text-ink"
            >
              {withCurves.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {thaiDateTime(r.started_at)} · {r.outcome === 'deployed' ? t('rt_outcome_deployed') : r.outcome === 'rejected' ? t('rt_outcome_rejected') : r.outcome}
                </option>
              ))}
            </select>
          )}
          <InfoTip text={t('lc_help')} align="right" />
        </div>
      }
    >
      {withCurves.length === 0 ? (
        <p className="py-6 text-center text-[13px] text-muted">{t('lc_none')}</p>
      ) : error ? (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {t('lb_error')}: {error}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-4">
            {charts.map((c) => (
              <EpochChart
                key={c.key}
                title={t(`lc_${c.key}`)}
                points={data?.curves[c.key] ?? []}
                digits={c.digits}
                bestEpoch={c.key === 'lr' ? null : bestEpoch}
                bestLabel={t('lc_best')}
              />
            ))}
          </div>
          <p className="mt-2 text-[12.5px] leading-snug text-slate-600">
            {t(model === 'lstm' ? 'lc_read_lstm' : 'lc_read_convlstm')}
            {bestEpoch !== null ? ` ${bestEpoch > 0 ? t('lc_best_note', { epoch: bestEpoch }) : t('lc_best_zero')}` : ''}
          </p>
        </>
      )}
    </Panel>
  );
}
