"use client";

import React, { useEffect, useState } from 'react';
import { BadgeCheckIcon, CloudIcon, CloudOffIcon, CircleHelpIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { useForecast } from '@/context/ForecastContext';
import { solarApi } from '@/services/api';
import { CLOUD_UI, LOSS_HIGH_FROM_PCT, LOSS_MEDIUM_FROM_PCT, TONE_CLASS, impactLevelOfLoss } from '@/lib/levels';
import { parseBackendDate } from '@/lib/time';

// The model reads a 64x64 px crop; the area of interest is the 5x5 px box at its centre.
const CROP_PX = 64;
const AOI_PX = 5;
const AOI_SIZE_PCT = (AOI_PX / CROP_PX) * 100;
const AOI_OFFSET_PCT = ((CROP_PX - AOI_PX) / 2 / CROP_PX) * 100;

const CLOCK = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Bangkok' });

type StatusKey = 'sat_ok' | 'sat_shifted' | 'sat_observed_only' | 'sat_missing' | 'sat_night' | 'sat_low_sun' | 'sat_model_unavailable';
const STATUS_KEY: Record<string, StatusKey> = {
  ok: 'sat_ok',
  shifted: 'sat_shifted',
  observed_only: 'sat_observed_only',
  missing: 'sat_missing',
  night: 'sat_night',
  low_sun: 'sat_low_sun',
  model_unavailable: 'sat_model_unavailable',
};

/** Cloud in the area around the station: cover and expected loss of irradiance, now and for the next steps. */
export function CloudPanel() {
  const t = useTranslations('common');
  const { prediction, chartGhiData, selectedStationId } = useForecast();
  const [image, setImage] = useState<{ url: string; lastModified: string | null } | null>(null);

  const predictedAt = prediction?.predicted_at;
  useEffect(() => {
    if (!selectedStationId) return;
    let cancelled = false;
    let created: string | null = null;
    solarApi.getSatelliteCrop(selectedStationId).then((img) => {
      if (cancelled) {
        if (img) URL.revokeObjectURL(img.url);
        return;
      }
      created = img?.url ?? null;
      setImage(img);
    });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [selectedStationId, predictedAt]);

  const nowPct = prediction?.cloud_coverage_now_pct ?? null;
  const level = prediction?.cloud_impact_level ?? null;
  const ui = level ? CLOUD_UI[level] : null;
  const usable = ['ok', 'shifted', 'observed_only'].includes(prediction?.satellite_status ?? '');
  const lossNow = prediction?.sat_ghi_loss_now_pct ?? null;
  const statusKey = prediction?.satellite_status ? STATUS_KEY[prediction.satellite_status] : undefined;
  const imageTime = image?.lastModified ? parseBackendDate(new Date(image.lastModified).toISOString()) : null;

  return (
    <Panel
      title={t('cloud_panel_title')}
      icon={<CloudIcon className="h-5 w-5 text-slate-600" />}
      className="h-full"
      action={<InfoTip text={t('help_cloud')} align="right" />}
    >
      <div className="grid min-h-0 flex-1 grid-cols-[1fr_auto] gap-4">
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-3">
            <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full ${ui ? TONE_CLASS[ui.tone].box : 'bg-slate-100'} border`}>
              {ui ? (
                <ui.icon className={`h-9 w-9 ${TONE_CLASS[ui.tone].icon}`} aria-hidden="true" />
              ) : (
                <CloudOffIcon className="h-9 w-9 text-slate-400" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0">
              <p className="text-[12.5px] font-medium text-slate-600">{t('cloud_now')}</p>
              <p className="text-[24px] font-bold leading-tight text-ink tabular-nums">
                {usable && nowPct !== null ? `${Math.round(nowPct)}%` : '—'}
              </p>
              <p className="text-[13px] font-semibold text-slate-700">
                {ui ? t(ui.labelKey) : t('cloud_unknown')}
                {usable && lossNow !== null ? ` · ${t('sat_loss_now', { pct: Math.round(lossNow) })}` : ''}
              </p>
            </div>
          </div>

          <p className="mt-2 text-[12.5px] leading-snug text-slate-700">
            {statusKey ? t(statusKey, { minutes: prediction?.satellite_lag_minutes ?? 0 }) : t('no_forecast_title')}
          </p>
          {usable && prediction?.sat_calibration_verified != null && (
            <p
              className={`mt-1.5 inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${
                prediction.sat_calibration_verified ? 'bg-ok-soft text-[#166534]' : 'bg-slate-100 text-slate-700'
              }`}
              title={
                !prediction.sat_calibration_verified
                  ? t('sat_unverified_tip')
                  : prediction.sat_calibration_check && !prediction.sat_calibration_check.fitted && prediction.sat_calibration_check.mae !== null
                  ? t('sat_checked_tip', { pairs: prediction.sat_calibration_check.pairs ?? 0, mae: prediction.sat_calibration_check.mae.toFixed(2) })
                  : t('sat_verified_tip')
              }
            >
              {prediction.sat_calibration_verified ? (
                <BadgeCheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <CircleHelpIcon className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {t(prediction.sat_calibration_verified ? 'sat_verified' : 'sat_unverified')}
            </p>
          )}

          {/* Forecast cloud cover per 10-minute step */}
          <div className="mt-auto pt-2">
            <p className="mb-1 text-[11.5px] font-semibold text-slate-600">{t('cloud_forecast')}</p>
            <div className="flex h-12 items-end gap-[2px]" role="img" aria-label={t('cloud_forecast')}>
              {chartGhiData.map((p) => {
                const lv = impactLevelOfLoss(p.lossPct);
                if (p.lossPct === null || !lv) {
                  return <span key={p.t} title={`${p.t} · ${t('no_data')}`} className="h-[2px] min-w-0 flex-1 bg-slate-200" />;
                }
                return (
                  <span
                    key={p.t}
                    title={`${p.t} · ${t('cloud_cover')} ${p.cloudPct ?? '—'}% · ${t('loss_short')} ${p.lossPct}% · ${t(CLOUD_UI[lv].labelKey)}`}
                    className="min-w-0 max-w-[24px] flex-1 rounded-t-[4px] hover:opacity-70"
                    style={{ height: `${Math.max(6, Math.min(100, p.lossPct))}%`, background: TONE_CLASS[CLOUD_UI[lv].tone].fill }}
                  />
                );
              })}
            </div>
            <div className="mt-0.5 flex justify-between text-[10.5px] text-muted">
              <span>{chartGhiData[0]?.t}</span>
              <span>{chartGhiData[chartGhiData.length - 1]?.t}</span>
            </div>
            <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-slate-700">
              {(['low', 'medium', 'high'] as const).map((lv) => {
                const Icon = CLOUD_UI[lv].icon;
                const range =
                  lv === 'low' ? `< ${LOSS_MEDIUM_FROM_PCT}%` : lv === 'medium' ? `${LOSS_MEDIUM_FROM_PCT}–${LOSS_HIGH_FROM_PCT}%` : `> ${LOSS_HIGH_FROM_PCT}%`;
                return (
                  <li key={lv} className="flex items-center gap-1 whitespace-nowrap">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: TONE_CLASS[CLOUD_UI[lv].tone].fill }} />
                    <Icon className="h-3.5 w-3.5 text-slate-600" aria-hidden="true" />
                    {t(CLOUD_UI[lv].labelKey)} ({t('loss_short')} {range})
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <figure className="flex w-[188px] shrink-0 flex-col">
          <div className="relative aspect-square w-full overflow-hidden rounded-lg border border-line bg-slate-900">
            {image ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={image.url} alt={t('sat_image_alt')} className="h-full w-full" style={{ imageRendering: 'pixelated' }} />
                <span
                  aria-hidden="true"
                  className="absolute border-2 border-white shadow-[0_0_0_1px_rgba(15,23,42,0.9)]"
                  style={{ left: `${AOI_OFFSET_PCT}%`, top: `${AOI_OFFSET_PCT}%`, width: `${AOI_SIZE_PCT}%`, height: `${AOI_SIZE_PCT}%` }}
                />
              </>
            ) : (
              <p className="flex h-full items-center justify-center px-3 text-center text-[12px] text-slate-300">{t('sat_image_none')}</p>
            )}
          </div>
          <figcaption className="mt-1 text-[11px] leading-snug text-muted">
            {t('aoi_caption')}
            {imageTime ? ` · ${CLOCK.format(imageTime)}` : ''}
          </figcaption>
        </figure>
      </div>
    </Panel>
  );
}
