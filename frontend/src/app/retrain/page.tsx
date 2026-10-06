"use client";

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { BanIcon, CheckCircle2Icon, CircleHelpIcon, HistoryIcon, RefreshCwIcon, RepeatIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { LearningCurves } from '@/components/UI/LearningCurves';
import { useAuth } from '@/context/AuthContext';
import { RetrainRun, RetrainStatus, dayViewApi, thaiDateTime } from '@/services/dayViewApi';

const REFRESH_MS = 60_000;
const KNOWN_REASONS = ['no_improvement_on_measured_ghi', 'worse_on_weather_only_validation', 'no_improvement_on_validation'] as const;

function Outcome({ run }: { run: RetrainRun }) {
  const t = useTranslations('common');
  const tone =
    run.outcome === 'deployed'
      ? { cls: 'bg-ok-soft text-[#166534]', icon: CheckCircle2Icon, label: t('rt_outcome_deployed') }
      : run.outcome === 'rejected'
      ? { cls: 'bg-slate-100 text-slate-700', icon: BanIcon, label: t('rt_outcome_rejected') }
      : { cls: 'bg-slate-100 text-slate-700', icon: CircleHelpIcon, label: run.outcome };
  const Icon = tone.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[12px] font-bold ${tone.cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {tone.label}
      {run.version ? ` v${run.version}` : ''}
    </span>
  );
}

const fixed = (v: number | null | undefined, digits: number) => (v === null || v === undefined ? '—' : v.toFixed(digits));
const beforeAfter = (a: unknown, b: unknown, digits: number) =>
  typeof a === 'number' && typeof b === 'number' ? `${a.toFixed(digits)} → ${b.toFixed(digits)}` : '—';
/** Runs before 6 Oct 2026 evening checked the model with measured GHI in its input: their real_mae is not comparable. */
const oldCheck = (r: RetrainRun) => r.metric === 'real_mae' && (r.details.min_improvement ?? null) === null;

/** Proof that both models are retrained: deployed versions, what is pending and every run with its verdict. */
export default function RetrainPage() {
  const t = useTranslations('common');
  const { isAdmin } = useAuth();
  const [status, setStatus] = useState<RetrainStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await dayViewApi.getRetrainStatus());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    load();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [isAdmin, load]);

  if (!isAdmin) {
    return (
      <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[14px] text-amber-800">
        {t('admin_only')}
      </div>
    );
  }

  const reasonText = (reason: string | null) =>
    !reason ? '' : (KNOWN_REASONS as readonly string[]).includes(reason) ? t(`rt_reason_${reason as (typeof KNOWN_REASONS)[number]}`) : reason;
  const lstm = status?.lstm;
  const conv = status?.convlstm;
  const daysPct = lstm?.new_days != null && lstm.days_needed ? Math.min(100, Math.round((lstm.new_days / lstm.days_needed) * 100)) : null;
  const batchPct = conv?.new_scans != null && conv.batch_size ? Math.min(100, Math.round((conv.new_scans / conv.batch_size) * 100)) : null;
  const count = (runs: RetrainRun[], outcome: string) => runs.filter((r) => r.outcome === outcome).length;
  const th = 'px-3 py-2';
  const td = 'px-3 py-1.5';

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 pb-4 text-ink">
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
          <RepeatIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('rt_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('rt_desc')}</p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-[13px] font-semibold text-slate-700 hover:bg-canvas disabled:opacity-50"
        >
          <RefreshCwIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {t('rt_refresh')}
        </button>
      </div>

      {error && (
        <p role="alert" className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {t('lb_error')}: {error}
        </p>
      )}
      {status && !status.retrain_enabled && (
        <p className="shrink-0 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">{t('rt_disabled')}</p>
      )}
      {status?.history_error && (
        <p className="shrink-0 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
          {t('rt_history_error')}: {status.history_error}
        </p>
      )}

      <div className="grid shrink-0 grid-cols-1 gap-3.5 xl:grid-cols-2">
        <Panel title={t('rt_lstm_title')} icon={<RepeatIcon className="h-5 w-5 text-brand" />}>
          <div className="grid grid-cols-2 gap-4 text-[13px] text-slate-700">
            <div>
              <p className="font-semibold text-ink">{t('fr_model')}</p>
              <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">{lstm?.model_version ? `v${lstm.model_version}` : '—'}</p>
              <p className="mt-1 text-[12px] text-slate-600">
                {lstm?.trained_at ? t('rt_since', { at: thaiDateTime(lstm.trained_at) }) : '—'}
                {lstm?.previous_version ? ` · ${t('rt_previous', { version: lstm.previous_version })}` : ''}
              </p>
            </div>
            <div>
              <p className="font-semibold text-ink">{t('rt_next')}</p>
              {lstm?.running ? (
                <p className="mt-0.5 font-semibold text-ink">{t('rt_state_running')}</p>
              ) : lstm?.new_days != null && lstm.days_needed ? (
                <>
                  <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">
                    {lstm.new_days} / {lstm.days_needed} <span className="text-[13px] font-semibold">{t('rt_days_unit')}</span>
                  </p>
                  <div
                    className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-200"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={lstm.days_needed}
                    aria-valuenow={Math.min(lstm.new_days, lstm.days_needed)}
                  >
                    <div className="h-full rounded-full bg-brand" style={{ width: `${daysPct}%` }} />
                  </div>
                </>
              ) : (
                <p className="mt-0.5 text-slate-600">{t('rt_lstm_idle')}</p>
              )}
              {lstm?.scheduled && !lstm.running && <p className="mt-1 text-[12px] font-semibold text-ink">{t('rt_lstm_scheduled')}</p>}
              <p className="mt-1 text-[12px] text-slate-600">
                {t('rt_lstm_trigger')}{' '}
                <Link href="/labeling" className="font-semibold text-brand underline">
                  {t('nav_labeling')}
                </Link>
              </p>
            </div>
          </div>
          <p className="mt-3 text-[12.5px] leading-snug text-slate-600">{t('rt_lstm_gate')}</p>
        </Panel>

        <Panel title={t('rt_convlstm_title')} icon={<RepeatIcon className="h-5 w-5 text-brand" />}>
          <div className="grid grid-cols-2 gap-4 text-[13px] text-slate-700">
            <div>
              <p className="font-semibold text-ink">{t('fr_model')}</p>
              <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">{conv?.model_version ? `v${conv.model_version}` : '—'}</p>
              <p className="mt-1 text-[12px] text-slate-600">{conv?.retrained_at ? t('rt_since', { at: thaiDateTime(conv.retrained_at) }) : t('fr_never_retrained')}</p>
            </div>
            <div>
              <p className="font-semibold text-ink">{t('rt_next')}</p>
              {conv?.running || conv?.scheduled ? (
                <p className="mt-0.5 font-semibold text-ink">{t(conv.running ? 'rt_state_running' : 'rt_convlstm_queued')}</p>
              ) : conv?.new_scans != null && conv.batch_size ? (
                <>
                  <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">
                    {conv.new_scans} / {conv.batch_size}
                  </p>
                  <div
                    className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-200"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={conv.batch_size}
                    aria-valuenow={Math.min(conv.new_scans, conv.batch_size)}
                  >
                    <div className="h-full rounded-full bg-brand" style={{ width: `${batchPct}%` }} />
                  </div>
                </>
              ) : (
                <p className="mt-0.5 text-slate-600">{t('fr_batch_unknown')}</p>
              )}
              <p className="mt-1 text-[12px] text-slate-600">
                {t('rt_convlstm_trigger')}{' '}
                <Link href="/frame-review" className="font-semibold text-brand underline">
                  {t('nav_frame_review')}
                </Link>{' '}
                · {t('fr_rejected_total', { n: conv?.rejected_frames_total ?? 0 })}
              </p>
            </div>
          </div>
          <p className="mt-3 text-[12.5px] leading-snug text-slate-600">{t('rt_convlstm_gate')}</p>
        </Panel>
      </div>

      {status && <LearningCurves model="lstm" runs={status.history.lstm} />}

      <Panel
        title={t('rt_history_lstm')}
        icon={<HistoryIcon className="h-5 w-5 text-brand" />}
        className="shrink-0"
        action={
          status && (
            <p className="text-[12.5px] text-slate-700">
              {t('rt_history_count', { total: status.history.lstm.length, deployed: count(status.history.lstm, 'deployed'), rejected: count(status.history.lstm, 'rejected') })}
            </p>
          )
        }
      >
        {!status || status.history.lstm.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-muted">{status ? t('rt_no_runs') : t('cp_loading')}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-line bg-canvas font-bold text-slate-700">
                <tr>
                  <th className={th}>{t('rt_col_time')}</th>
                  <th className={th}>{t('rt_col_outcome')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_real_mae')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_val_mae')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_labels')}</th>
                  <th className={th}>{t('rt_col_holdout')}</th>
                  <th className={th}>{t('rt_col_note')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white text-slate-700">
                {status.history.lstm.map((r) => (
                  <tr key={r.started_at}>
                    <td className={`${td} whitespace-nowrap font-medium tabular-nums text-ink`}>{thaiDateTime(r.started_at)}</td>
                    <td className={td}>
                      <Outcome run={r} />
                    </td>
                    <td className={`${td} text-right tabular-nums`}>
                      {r.metric === 'real_mae' ? `${fixed(r.before, 1)} → ${fixed(r.after, 1)}${oldCheck(r) ? ' *' : ''}` : '—'}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{beforeAfter(r.details.val_mae_before, r.details.val_mae_after, 1)}</td>
                    <td className={`${td} text-right tabular-nums`}>{r.details.label_count ?? '—'}</td>
                    <td className={`${td} whitespace-nowrap tabular-nums`}>
                      {r.details.holdout_day ?? '—'}
                      {(r.details.test_days ?? r.details.measured_days) ? ` (${r.details.test_days ?? r.details.measured_days} ${t('rt_days_unit')})` : ''}
                    </td>
                    <td className={td}>{r.outcome === 'rejected' ? reasonText(r.reason) : r.gate === 'measured_ghi' ? t('rt_gate_measured') : t('rt_gate_weather')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[12px] leading-snug text-slate-600">{t('rt_lstm_cols_help')}</p>
        {status?.history.lstm.some(oldCheck) && <p className="mt-1 text-[12px] leading-snug text-slate-600">{t('rt_lstm_old_check_note')}</p>}
      </Panel>

      {status && <LearningCurves model="convlstm" runs={status.history.convlstm} />}

      <Panel
        title={t('rt_history_convlstm')}
        icon={<HistoryIcon className="h-5 w-5 text-brand" />}
        className="shrink-0"
        action={
          status && (
            <p className="text-[12.5px] text-slate-700">
              {t('rt_history_count', { total: status.history.convlstm.length, deployed: count(status.history.convlstm, 'deployed'), rejected: count(status.history.convlstm, 'rejected') })}
            </p>
          )
        }
      >
        {!status || status.history.convlstm.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-muted">{status ? t('rt_no_runs') : t('cp_loading')}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-line bg-canvas font-bold text-slate-700">
                <tr>
                  <th className={th}>{t('rt_col_time')}</th>
                  <th className={th}>{t('rt_col_outcome')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_mse')}</th>
                  <th className={`${th} text-right`}>SSIM</th>
                  <th className={`${th} text-right`}>{t('rt_col_aoi')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_frames')}</th>
                  <th className={`${th} text-right`}>{t('rt_col_sequences')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line bg-white text-slate-700">
                {status.history.convlstm.map((r) => (
                  <tr key={r.started_at}>
                    <td className={`${td} whitespace-nowrap font-medium tabular-nums text-ink`}>{thaiDateTime(r.started_at)}</td>
                    <td className={td}>
                      <Outcome run={r} />
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{`${fixed(r.before, 4)} → ${fixed(r.after, 4)}`}</td>
                    <td className={`${td} text-right tabular-nums`}>{beforeAfter(r.details.ssim_before, r.details.ssim_after, 2)}</td>
                    <td className={`${td} text-right tabular-nums`}>{beforeAfter(r.details.aoi_cloud_mae_before, r.details.aoi_cloud_mae_after, 1)}</td>
                    <td className={`${td} text-right tabular-nums`}>{r.details.frames_used ?? '—'}</td>
                    <td className={`${td} text-right tabular-nums`}>
                      {r.details.train_sequences ?? '—'} / {r.details.val_sequences ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[12px] leading-snug text-slate-600">{t('rt_convlstm_cols_help')}</p>
      </Panel>
    </div>
  );
}
