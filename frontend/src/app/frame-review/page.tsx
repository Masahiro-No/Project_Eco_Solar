"use client";

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangleIcon, BanIcon, CheckIcon, RefreshCwIcon, SatelliteIcon, SaveIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { useAuth } from '@/context/AuthContext';
import { solarApi, StationResponse } from '@/services/api';
import { LabelingApiError } from '@/services/labelingApi';
import {
  ConvLstmStatus,
  FrameFlag,
  FrameItem,
  FrameListResponse,
  ReviewItem,
  ReviewReason,
  ReviewStatus,
  frameReviewApi,
} from '@/services/frameReviewApi';

const TH_OFFSET_MS = 7 * 3600 * 1000;
const todayThai = () => new Date(Date.now() + TH_OFFSET_MS).toISOString().slice(0, 10);
const hhmm = (iso: string) => {
  const d = new Date(new Date(iso).getTime() + TH_OFFSET_MS);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
};

// The model reads a 64x64 px crop; the area of interest is the 5x5 px box at its centre.
const AOI_SIZE_PCT = (5 / 64) * 100;
const AOI_OFFSET_PCT = ((64 - 5) / 2 / 64) * 100;

const REASONS: ReviewReason[] = ['blank', 'partial', 'artifact', 'glare', 'other'];
type Pending = { status: ReviewStatus; reason: ReviewReason };

const reasonFor = (flags: FrameFlag[]): ReviewReason => (flags.includes('blank') ? 'blank' : flags.includes('partial') ? 'partial' : 'artifact');

/** Human check of the real satellite frames: a rejected frame is left out of the next ConvLSTM retrain. */
export default function FrameReviewPage() {
  const t = useTranslations('common');
  const { isAdmin } = useAuth();
  const [stations, setStations] = useState<StationResponse[]>([]);
  const [stationId, setStationId] = useState('');
  const [date, setDate] = useState(todayThai());
  const [data, setData] = useState<FrameListResponse | null>(null);
  const [status, setStatus] = useState<ConvLstmStatus | null>(null);
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fail = useCallback(
    (e: unknown) => setError(e instanceof LabelingApiError && e.status === 401 ? t('lb_login_required') : `${t('lb_error')}: ${e instanceof Error ? e.message : String(e)}`),
    [t],
  );

  const load = useCallback(async () => {
    if (!stationId) return;
    setLoading(true);
    setError(null);
    try {
      setData(await frameReviewApi.getFrames(stationId, date));
      setPending({});
    } catch (e) {
      setData(null);
      fail(e);
    } finally {
      setLoading(false);
    }
  }, [stationId, date, fail]);

  useEffect(() => {
    if (!isAdmin) return;
    solarApi.getStations().then((s) => {
      setStations(s);
      if (s.length) setStationId((cur) => cur || s[0].id);
    });
    frameReviewApi.getStatus().then(setStatus).catch(() => setStatus(null));
  }, [isAdmin]);

  useEffect(() => {
    if (isAdmin) load();
  }, [load, isAdmin]);

  const frames = useMemo(() => (data?.frames ?? []).filter((f) => !onlyFlagged || f.flags.length > 0), [data, onlyFlagged]);
  const pendingCount = Object.keys(pending).length;

  const decide = (f: FrameItem, next: ReviewStatus) => {
    setMessage(null);
    setPending((cur) => {
      const copy = { ...cur };
      const saved = f.review?.status ?? null;
      const current = copy[f.timestamp]?.status ?? saved;
      if (current === next && copy[f.timestamp]) {
        delete copy[f.timestamp]; // clicking the pending choice again withdraws it
      } else if (saved === next) {
        delete copy[f.timestamp]; // back to what is already saved
      } else {
        copy[f.timestamp] = { status: next, reason: copy[f.timestamp]?.reason ?? reasonFor(f.flags) };
      }
      return copy;
    });
  };

  const rejectAllFlagged = () => {
    setMessage(null);
    setPending((cur) => {
      const copy = { ...cur };
      for (const f of data?.frames ?? []) {
        if (f.flags.length > 0 && !f.review && !copy[f.timestamp]) copy[f.timestamp] = { status: 'rejected', reason: reasonFor(f.flags) };
      }
      return copy;
    });
  };

  // Frames without an automatic hint are marked as usable; the flagged ones are left for the reviewer to look at
  const acceptAllUnflagged = () => {
    setMessage(null);
    setPending((cur) => {
      const copy = { ...cur };
      for (const f of data?.frames ?? []) {
        if (f.flags.length === 0 && !f.review && !copy[f.timestamp]) copy[f.timestamp] = { status: 'accepted', reason: reasonFor(f.flags) };
      }
      return copy;
    });
  };
  const unreviewedClean = (data?.frames ?? []).filter((f) => f.flags.length === 0 && !f.review && !pending[f.timestamp]).length;

  const save = async () => {
    if (!stationId || pendingCount === 0) return;
    setBusy(true);
    setError(null);
    try {
      const items: ReviewItem[] = Object.entries(pending).map(([timestamp, p]) => ({
        timestamp,
        status: p.status,
        ...(p.status === 'rejected' ? { reason: p.reason } : {}),
      }));
      const res = await frameReviewApi.submit(stationId, items);
      setMessage(t('fr_saved', { saved: res.saved, rejected: res.rejected, accepted: res.accepted }));
      await load();
      frameReviewApi.getStatus().then(setStatus).catch(() => undefined);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  if (!isAdmin) {
    return (
      <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[14px] text-amber-800">
        {t('admin_only')}
      </div>
    );
  }

  const batchPct = status?.new_scans != null && status.batch_size ? Math.min(100, Math.round((status.new_scans / status.batch_size) * 100)) : null;
  const last = status?.last_result ?? null;

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 pb-4 text-ink">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
          <SatelliteIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('fr_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('fr_desc')}</p>
        </div>
      </div>

      <Panel
        title={t('fr_status_title')}
        icon={<SatelliteIcon className="h-5 w-5 text-brand" />}
        className="shrink-0"
        action={
          <Link href="/retrain" className="text-[12.5px] font-semibold text-brand underline">
            {t('rt_open_page')}
          </Link>
        }
      >
        <div className="grid grid-cols-1 gap-4 text-[13px] text-slate-700 md:grid-cols-3">
          <div>
            <p className="font-semibold text-ink">{t('fr_batch')}</p>
            {status?.new_scans != null && status.batch_size ? (
              <>
                <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">
                  {status.new_scans} / {status.batch_size}
                </p>
                <div
                  className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-200"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={status.batch_size}
                  aria-valuenow={Math.min(status.new_scans, status.batch_size)}
                >
                  <div className="h-full rounded-full bg-brand" style={{ width: `${batchPct}%` }} />
                </div>
                <p className="mt-1 text-[12px] text-slate-600">{status.retrain_enabled ? t('fr_batch_note') : t('fr_retrain_off')}</p>
              </>
            ) : (
              <p className="mt-0.5 text-slate-600">{t('fr_batch_unknown')}</p>
            )}
          </div>
          <div>
            <p className="font-semibold text-ink">{t('fr_model')}</p>
            <p className="mt-0.5 text-[20px] font-bold tabular-nums text-ink">{status?.model_version ? `v${status.model_version}` : '—'}</p>
            <p className="mt-1 text-[12px] text-slate-600">
              {status?.retrained_at ? t('fr_retrained_at', { at: status.retrained_at }) : t('fr_never_retrained')}
            </p>
          </div>
          <div>
            <p className="font-semibold text-ink">{t('fr_last_run')}</p>
            {last ? (
              <>
                <p className="mt-0.5 font-semibold text-ink">
                  {last.status === 'deployed' ? t('fr_run_deployed') : last.status === 'rejected' ? t('fr_run_rejected') : last.status}
                  {last.finished_at ? ` · ${last.finished_at}` : ''}
                </p>
                {last.baseline && last.candidate && (
                  <p className="mt-1 text-[12px] tabular-nums text-slate-600">
                    MSE {last.baseline.mse.toFixed(4)} → {last.candidate.mse.toFixed(4)} · {t('fr_sequences', { n: last.train_sequences ?? 0 })}
                  </p>
                )}
              </>
            ) : (
              <p className="mt-0.5 text-slate-600">{t('fr_no_run_yet')}</p>
            )}
            <p className="mt-1 text-[12px] text-slate-600">{t('fr_rejected_total', { n: status?.rejected_frames_total ?? 0 })}</p>
          </div>
        </div>
      </Panel>

      <Panel
        title={t('fr_frames_title')}
        icon={<SatelliteIcon className="h-5 w-5 text-brand" />}
        className="shrink-0"
        action={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <select
              aria-label={t('lb_station')}
              value={stationId}
              onChange={(e) => setStationId(e.target.value)}
              className="h-9 rounded-lg border border-line bg-white px-2 text-[13px] text-ink"
            >
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} — {s.name}
                </option>
              ))}
            </select>
            <input
              aria-label={t('lb_date')}
              type="date"
              value={date}
              max={todayThai()}
              onChange={(e) => setDate(e.target.value)}
              className="h-9 rounded-lg border border-line bg-white px-2 text-[13px] text-ink"
            />
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-[13px] font-semibold text-slate-700 hover:bg-canvas disabled:opacity-50"
            >
              <RefreshCwIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              {t('lb_load')}
            </button>
          </div>
        }
      >
        <p className="text-[12.5px] leading-snug text-slate-600">{t('fr_how')}</p>

        {error && (
          <p role="alert" className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="mt-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-[13px] text-green-800">
            {message}
          </p>
        )}

        {data && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[13px] text-slate-700">
            <p>
              {t('fr_summary', { day: data.daytime_frames, flagged: data.flagged, rejected: data.rejected, night: data.night_frames })}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5">
                <input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />
                {t('fr_only_flagged')}
              </label>
              <button
                type="button"
                onClick={acceptAllUnflagged}
                disabled={unreviewedClean === 0}
                title={t('fr_accept_clean_tip')}
                className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 font-semibold text-slate-700 hover:bg-canvas disabled:opacity-50"
              >
                <CheckIcon className="h-4 w-4" aria-hidden="true" />
                {t('fr_accept_clean', { n: unreviewedClean })}
              </button>
              <button
                type="button"
                onClick={rejectAllFlagged}
                disabled={!data.flagged}
                className="h-9 rounded-lg border border-line bg-white px-3 font-semibold text-slate-700 hover:bg-canvas disabled:opacity-50"
              >
                {t('fr_reject_flagged')}
              </button>
              <button
                type="button"
                onClick={save}
                disabled={busy || pendingCount === 0}
                className="flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 font-bold text-white hover:bg-brand/90 disabled:opacity-50"
              >
                <SaveIcon className="h-4 w-4" />
                {t('fr_save', { n: pendingCount })}
              </button>
            </div>
          </div>
        )}

        {data && frames.length === 0 && <p className="py-8 text-center text-[13px] text-muted">{t('fr_no_frames')}</p>}

        <ul className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
          {frames.map((f) => {
            const p = pending[f.timestamp];
            const state: ReviewStatus | null = p?.status ?? f.review?.status ?? null;
            const ring = state === 'rejected' ? 'border-bad ring-2 ring-bad/30' : state === 'accepted' ? 'border-ok' : f.flags.length ? 'border-warn' : 'border-line';
            return (
              <li key={f.timestamp} className={`flex flex-col gap-1.5 rounded-lg border bg-white p-2 ${ring}`}>
                <div className="relative aspect-square w-full overflow-hidden rounded-md bg-slate-900">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${f.image_b64}`}
                    alt={t('fr_image_alt', { time: hhmm(f.timestamp) })}
                    className="h-full w-full"
                    style={{ imageRendering: 'pixelated' }}
                  />
                  <span
                    aria-hidden="true"
                    className="absolute border-2 border-white shadow-[0_0_0_1px_rgba(15,23,42,0.9)]"
                    style={{ left: `${AOI_OFFSET_PCT}%`, top: `${AOI_OFFSET_PCT}%`, width: `${AOI_SIZE_PCT}%`, height: `${AOI_SIZE_PCT}%` }}
                  />
                </div>
                <div className="flex items-baseline justify-between text-[12.5px]">
                  <span className="font-bold tabular-nums text-ink">{hhmm(f.timestamp)}</span>
                  <span className="tabular-nums text-slate-600">{f.cloud_pct === null ? '—' : `${t('cloud_cover')} ${Math.round(f.cloud_pct)}%`}</span>
                </div>
                {f.flags.length > 0 && (
                  <p className="flex flex-wrap items-center gap-1 text-[11.5px] font-semibold text-[#92400e]">
                    <AlertTriangleIcon className="h-3.5 w-3.5 text-warn" aria-hidden="true" />
                    {f.flags.map((flag) => t(`fr_flag_${flag}`)).join(' · ')}
                  </p>
                )}
                <div className="mt-auto grid grid-cols-2 gap-1">
                  <button
                    type="button"
                    aria-pressed={state === 'accepted'}
                    onClick={() => decide(f, 'accepted')}
                    className={`flex h-8 items-center justify-center gap-1 rounded-md border text-[12px] font-semibold ${
                      state === 'accepted' ? 'border-ok bg-ok-soft text-[#166534]' : 'border-line bg-white text-slate-700 hover:bg-canvas'
                    }`}
                  >
                    <CheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('fr_ok')}
                  </button>
                  <button
                    type="button"
                    aria-pressed={state === 'rejected'}
                    onClick={() => decide(f, 'rejected')}
                    className={`flex h-8 items-center justify-center gap-1 rounded-md border text-[12px] font-semibold ${
                      state === 'rejected' ? 'border-bad bg-bad-soft text-[#991b1b]' : 'border-line bg-white text-slate-700 hover:bg-canvas'
                    }`}
                  >
                    <BanIcon className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('fr_bad')}
                  </button>
                </div>
                {p?.status === 'rejected' ? (
                  <select
                    aria-label={t('fr_reason')}
                    value={p.reason}
                    onChange={(e) => setPending((cur) => ({ ...cur, [f.timestamp]: { status: 'rejected', reason: e.target.value as ReviewReason } }))}
                    className="h-8 rounded-md border border-line bg-white px-1.5 text-[12px] text-ink"
                  >
                    {REASONS.map((r) => (
                      <option key={r} value={r}>
                        {t(`fr_reason_${r}`)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="min-h-4 text-[11.5px] text-slate-600">
                    {p
                      ? t('fr_pending')
                      : f.review
                      ? `${t(f.review.status === 'rejected' ? 'fr_saved_bad' : 'fr_saved_ok')}${
                          f.review.status === 'rejected' && f.review.reason ? ` · ${t(`fr_reason_${f.review.reason as ReviewReason}`)}` : ''
                        }`
                      : ''}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}
