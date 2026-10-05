"use client";

import React, { useEffect, useState } from 'react';
import { BadgeCheckIcon, CircleHelpIcon, HourglassIcon, RulerIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { CalibrationStatus, dayViewApi, thaiDateTime } from '@/services/dayViewApi';

const POLL_PENDING_MS = 15_000;

/**
 * Has the satellite-to-irradiance relation been compared with this station's measured GHI?
 * The check runs by itself about a minute after measured values are saved; this panel shows its result and,
 * when there are too few usable pairs, how many are still missing.
 */
export function CalibrationStatusPanel({ stationId, refreshKey }: { stationId: string; refreshKey?: unknown }) {
  const t = useTranslations('common');
  const [status, setStatus] = useState<CalibrationStatus | null>(null);
  const [saved, setSaved] = useState(false);

  // a save just happened: the check is scheduled, so keep asking until it has run
  useEffect(() => {
    if (refreshKey) setSaved(true);
  }, [refreshKey]);

  useEffect(() => {
    if (!stationId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = () =>
      dayViewApi
        .getCalibrationStatus(stationId)
        .then((s) => {
          if (!alive) return;
          setStatus(s);
          if (s.pending) timer = setTimeout(load, POLL_PENDING_MS);
          else setSaved(false);
        })
        .catch(() => {
          if (alive) setStatus(null);
        });
    setStatus(null);
    load();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [stationId, refreshKey]);

  const verified = status?.state === 'fitted' || status?.state === 'checked';
  const missing = status && status.state === 'insufficient' ? Math.max(0, status.min_pairs - (status.pairs ?? 0)) : 0;
  const Icon = status?.pending ? HourglassIcon : verified ? BadgeCheckIcon : CircleHelpIcon;
  const chip = status?.pending ? 'bg-brand-soft text-brand' : verified ? 'bg-ok-soft text-[#166534]' : 'bg-slate-100 text-slate-700';

  return (
    <Panel
      title={t('cal_title')}
      icon={<RulerIcon className="h-5 w-5 text-brand" />}
      className="shrink-0"
      action={<InfoTip text={t('cal_help', { min: status?.min_pairs ?? 30 })} align="right" />}
    >
      {!status ? (
        <p className="text-[13px] text-slate-600">—</p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px] text-slate-700">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12.5px] font-bold ${chip}`}>
            <Icon className="h-4 w-4" aria-hidden="true" />
            {status.pending ? t('cal_pending') : t(`cal_state_${status.state}`)}
          </span>
          <p className="min-w-[260px] flex-1 leading-snug">
            {status.state === 'fitted' && t('cal_detail_fitted', { pairs: status.pairs ?? 0, mae: (status.mae ?? 0).toFixed(2) })}
            {status.state === 'checked' && t('cal_detail_checked', { pairs: status.pairs ?? 0, mae: (status.mae ?? 0).toFixed(2) })}
            {status.state === 'insufficient' && t('cal_detail_insufficient', { pairs: status.pairs ?? 0, min: status.min_pairs, missing })}
            {status.state === 'not_checked' && t(saved || status.pending ? 'cal_detail_waiting' : 'cal_detail_not_checked')}
            {status.state === 'no_calibration' && t('cal_detail_no_file')}
          </p>
          <p className="text-[12px] text-slate-600">
            {status.pending ? t('cal_pending_note') : status.checked_at ? t('cal_checked_at', { at: thaiDateTime(status.checked_at) }) : ''}
          </p>
        </div>
      )}
    </Panel>
  );
}
