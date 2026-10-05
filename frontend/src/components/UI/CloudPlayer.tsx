"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeftIcon, ChevronRightIcon, FilmIcon, PauseIcon, PlayIcon, SkipForwardIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { isSatelliteStatus } from '@/lib/levels';
import { DayFramesResponse, hhmmThai } from '@/services/dayViewApi';

// The model reads a 64x64 px crop; the area of interest is the 5x5 px box at its centre.
const AOI_SIZE_PCT = (5 / 64) * 100;
const AOI_OFFSET_PCT = ((64 - 5) / 2 / 64) * 100;
const SPEEDS = [1, 2, 4] as const;
const BASE_FRAME_MS = 500;

type Shot = { ms: number; image: string; cloudPct: number | null; predicted: boolean; leadMinutes: number | null };

/**
 * Plays the real Band 03 frames of the day and then the frames the ConvLSTM predicted in the newest round.
 * A predicted frame is always marked as such: it is model output, not an observation.
 */
export function CloudPlayer({ data, loading }: { data: DayFramesResponse | null; loading: boolean }) {
  const t = useTranslations('common');
  const shots = useMemo<Shot[]>(() => {
    if (!data) return [];
    const real = data.frames.map((f) => ({ ms: Date.parse(f.timestamp), image: f.image_b64, cloudPct: f.cloud_pct, predicted: false, leadMinutes: null }));
    const lastReal = real.length ? real[real.length - 1].ms : 0;
    const predicted = (data.forecast?.frames ?? [])
      .map((f) => ({ ms: Date.parse(f.timestamp), image: f.image_b64, cloudPct: f.cloud_pct, predicted: true, leadMinutes: f.lead_minutes }))
      .filter((f) => f.ms > lastReal); // a real frame that has arrived replaces the prediction of that time
    return [...real, ...predicted];
  }, [data]);

  const realCount = shots.filter((s) => !s.predicted).length;
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(2);

  // New data: stay on the newest real frame unless the user is looking at something else
  const followLatest = useRef(true);
  useEffect(() => {
    if (followLatest.current || index >= shots.length) setIndex(Math.max(0, realCount - 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shots.length, realCount]);

  useEffect(() => {
    if (!playing || shots.length < 2) return;
    const id = setInterval(() => {
      setIndex((i) => {
        if (i + 1 >= shots.length) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, BASE_FRAME_MS / speed);
    return () => clearInterval(id);
  }, [playing, speed, shots.length]);

  const go = (i: number) => {
    followLatest.current = false;
    setPlaying(false);
    setIndex(Math.min(shots.length - 1, Math.max(0, i)));
  };
  const toggle = () => {
    followLatest.current = false;
    if (!playing && index >= shots.length - 1) setIndex(0); // at the end: start over
    setPlaying((p) => !p);
  };

  const shot = shots[index] ?? null;
  const forecast = data?.forecast ?? null;
  const predictedCount = shots.length - realCount;
  const realSharePct = shots.length ? (realCount / shots.length) * 100 : 100;

  return (
    <Panel
      title={t('cp_title')}
      icon={<FilmIcon className="h-5 w-5 text-slate-600" />}
      className="h-full"
      action={<InfoTip text={t('cp_help')} align="right" />}
    >
      {!shot ? (
        <p className="flex flex-1 items-center justify-center text-center text-[13px] text-muted">{loading ? t('cp_loading') : t('cp_no_frames')}</p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="flex min-h-0 flex-1 gap-3">
            <div className="relative aspect-square h-full max-h-[260px] shrink-0 overflow-hidden rounded-lg bg-slate-900">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${shot.image}`}
                alt={t(shot.predicted ? 'cp_alt_predicted' : 'cp_alt_real', { time: hhmmThai(shot.ms) })}
                className="h-full w-full"
                style={{ imageRendering: 'pixelated' }}
              />
              <span
                aria-hidden="true"
                className="absolute border-2 border-white shadow-[0_0_0_1px_rgba(15,23,42,0.9)]"
                style={{ left: `${AOI_OFFSET_PCT}%`, top: `${AOI_OFFSET_PCT}%`, width: `${AOI_SIZE_PCT}%`, height: `${AOI_SIZE_PCT}%` }}
              />
              <span
                className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11.5px] font-bold ${
                  shot.predicted ? 'bg-brand text-white' : 'bg-white text-slate-800'
                }`}
              >
                {t(shot.predicted ? 'cp_badge_predicted' : 'cp_badge_real')}
              </span>
            </div>

            <div className="flex min-w-0 flex-1 flex-col justify-between text-[13px] text-slate-700">
              <div>
                <p className="text-[26px] font-bold leading-none tabular-nums text-ink">{hhmmThai(shot.ms)}</p>
                <p className="mt-1 font-semibold text-ink">
                  {shot.predicted
                    ? t('cp_predicted_line', { lead: shot.leadMinutes ?? 0, from: forecast?.end_time ? hhmmThai(Date.parse(forecast.end_time)) : '—' })
                    : t('cp_real_line')}
                </p>
                <p className="mt-1 tabular-nums">
                  {t('cloud_cover')}: <b className="text-ink">{shot.cloudPct === null ? '—' : `${Math.round(shot.cloudPct)}%`}</b>
                </p>
                <p className="mt-1 text-[12px] text-slate-600">{t('cp_frame_of', { n: index + 1, total: shots.length })}</p>
              </div>
              <p className="text-[12px] leading-snug text-slate-600">
                {predictedCount > 0 && forecast?.end_time
                  ? t('cp_forecast_note', {
                      n: predictedCount,
                      from: hhmmThai(Date.parse(forecast.end_time)),
                      version: forecast.model_version ?? '—',
                    })
                  : forecast
                  ? t('cp_no_forecast_round', { status: isSatelliteStatus(forecast.status) ? t(`sat_short_${forecast.status}`) : forecast.status })
                  : t('cp_no_forecast_day')}
              </p>
            </div>
          </div>

          <div className="shrink-0">
            {/* track: grey = real frames, blue = predicted frames */}
            <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-brand/70" aria-hidden="true">
              <div className="absolute inset-y-0 left-0 bg-slate-400" style={{ width: `${realSharePct}%` }} />
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(0, shots.length - 1)}
              step={1}
              value={index}
              onChange={(e) => go(Number(e.target.value))}
              aria-label={t('cp_slider')}
              aria-valuetext={`${hhmmThai(shot.ms)} ${t(shot.predicted ? 'cp_badge_predicted' : 'cp_badge_real')}`}
              className="mt-1 w-full accent-brand"
            />
            <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => go(index - 1)}
                  disabled={index === 0}
                  aria-label={t('cp_prev')}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-white text-slate-700 hover:bg-canvas disabled:opacity-40"
                >
                  <ChevronLeftIcon className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={toggle}
                  disabled={shots.length < 2}
                  className="flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-[13px] font-bold text-white hover:bg-brand/90 disabled:opacity-40"
                >
                  {playing ? <PauseIcon className="h-4 w-4" /> : <PlayIcon className="h-4 w-4" />}
                  {t(playing ? 'cp_pause' : 'cp_play')}
                </button>
                <button
                  type="button"
                  onClick={() => go(index + 1)}
                  disabled={index >= shots.length - 1}
                  aria-label={t('cp_next')}
                  className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-white text-slate-700 hover:bg-canvas disabled:opacity-40"
                >
                  <ChevronRightIcon className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    go(realCount - 1);
                    followLatest.current = true;
                  }}
                  disabled={realCount === 0}
                  className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 text-[12.5px] font-semibold text-slate-700 hover:bg-canvas disabled:opacity-40"
                >
                  <SkipForwardIcon className="h-4 w-4" />
                  {t('cp_latest_real')}
                </button>
              </div>
              <div className="flex items-center gap-1 text-[12.5px] text-slate-700" role="group" aria-label={t('cp_speed')}>
                <span className="mr-1">{t('cp_speed')}</span>
                {SPEEDS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={speed === s}
                    onClick={() => setSpeed(s)}
                    className={`h-8 rounded-md border px-2 font-semibold tabular-nums ${
                      speed === s ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-white text-slate-700 hover:bg-canvas'
                    }`}
                  >
                    {s}×
                  </button>
                ))}
              </div>
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 text-[11.5px] text-slate-600">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-4 rounded-full bg-slate-400" /> {t('cp_legend_real', { n: realCount })}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-4 rounded-full bg-brand/70" /> {t('cp_legend_predicted', { n: predictedCount })}
              </span>
              {data && data.blank_frames > 0 && <span>{t('cp_blank_note', { n: data.blank_frames })}</span>}
            </p>
          </div>
        </div>
      )}
    </Panel>
  );
}
