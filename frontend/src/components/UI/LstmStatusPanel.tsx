"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { RepeatIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { RetrainStatus, dayViewApi, thaiDateTime } from '@/services/dayViewApi';

const KNOWN_REASONS = ['no_improvement_on_measured_ghi', 'worse_on_weather_only_validation', 'no_improvement_on_validation'] as const;

/** The LSTM in use, whether a retrain is pending and how the last one ended (admin pages only). */
export function LstmStatusPanel({ refreshKey }: { refreshKey?: unknown }) {
  const t = useTranslations('common');
  const [status, setStatus] = useState<RetrainStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      dayViewApi
        .getRetrainStatus()
        .then((s) => {
          if (alive) setStatus(s);
        })
        .catch(() => undefined);
    load();
    // a saved label schedules a retrain a few minutes later: keep the state fresh while the page is open
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') load();
    }, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [refreshKey]);

  const lstm = status?.lstm;
  const last = status?.history.lstm[0] ?? null;
  const reason = last?.reason
    ? (KNOWN_REASONS as readonly string[]).includes(last.reason)
      ? t(`rt_reason_${last.reason as (typeof KNOWN_REASONS)[number]}`)
      : last.reason
    : null;

  return (
    <Panel
      title={t('rt_lstm_title')}
      icon={<RepeatIcon className="h-5 w-5 text-brand" />}
      className="shrink-0"
      action={
        <Link href="/retrain" className="text-[12.5px] font-semibold text-brand underline">
          {t('rt_open_page')}
        </Link>
      }
    >
      <div className="grid grid-cols-1 gap-4 text-[13px] text-slate-700 md:grid-cols-3">
        <div>
          <p className="font-semibold text-ink">{t('fr_model')}</p>
          <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">{lstm?.model_version ? `v${lstm.model_version}` : '—'}</p>
          <p className="mt-1 text-[12px] text-slate-600">{lstm?.trained_at ? t('rt_since', { at: thaiDateTime(lstm.trained_at) }) : '—'}</p>
        </div>
        <div>
          <p className="font-semibold text-ink">{t('rt_next')}</p>
          <p className="mt-0.5 font-semibold text-ink">
            {!status ? '—' : !status.retrain_enabled ? t('fr_retrain_off') : lstm?.running ? t('rt_state_running') : lstm?.scheduled ? t('rt_lstm_scheduled') : t('rt_lstm_idle')}
          </p>
          <p className="mt-1 text-[12px] text-slate-600">{t('rt_lstm_trigger_short')}</p>
        </div>
        <div>
          <p className="font-semibold text-ink">{t('fr_last_run')}</p>
          {last ? (
            <>
              <p className="mt-0.5 font-semibold text-ink">
                {last.outcome === 'deployed' ? t('rt_outcome_deployed') : last.outcome === 'rejected' ? t('rt_outcome_rejected') : last.outcome}
                {' · '}
                {thaiDateTime(last.started_at)}
              </p>
              <p className="mt-1 text-[12px] tabular-nums text-slate-600">
                {last.metric === 'real_mae' ? t('rt_col_real_mae') : t('rt_col_val_mae')}: {last.before?.toFixed(1) ?? '—'} → {last.after?.toFixed(1) ?? '—'}
                {reason ? ` · ${reason}` : ''}
              </p>
            </>
          ) : (
            <p className="mt-0.5 text-slate-600">{status ? t('rt_no_runs') : '—'}</p>
          )}
        </div>
      </div>
    </Panel>
  );
}
