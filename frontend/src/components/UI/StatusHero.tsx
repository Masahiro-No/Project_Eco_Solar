"use client";

import React from 'react';
import { HourglassIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useForecast } from '@/context/ForecastContext';
import { alertUi, TONE_CLASS } from '@/lib/levels';
import { useForecastAge } from './ForecastFreshness';

const kw = (v: number) => Math.round(v).toLocaleString();

/** The one thing to read first: alert level, what to do, and how much reserve. */
export function StatusHero() {
  const t = useTranslations('common');
  const { prediction, isLoading, selectedStation, stationsLoaded } = useForecast();
  const { ageMin, stale, runLabel } = useForecastAge();

  // An overdue forecast is not the state now (after a restart the newest one can be hours old)
  if (prediction && stale) {
    const then = alertUi(prediction.alert_level);
    return (
      <section role="status" aria-live="polite" className="flex shrink-0 items-center gap-5 rounded-xl border border-line bg-white px-5 py-4 shadow-sm">
        <span className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-slate-100">
          <HourglassIcon className="h-11 w-11 text-slate-400" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold text-slate-600">{selectedStation?.name ?? prediction.station_name}</p>
          <p className="text-[20px] font-bold leading-tight text-ink">{t('stale_title')}</p>
          <p className="mt-1 text-[14px] leading-snug text-slate-700">{t('stale_desc', { time: runLabel, minutes: ageMin ?? 0 })}</p>
          <p className="mt-0.5 text-[12.5px] text-slate-600">
            {t('stale_then', { status: then ? t(then.labelKey) : prediction.alert_level })}
          </p>
        </div>
      </section>
    );
  }

  if (!prediction) {
    const message = isLoading || !stationsLoaded ? t('loading') : selectedStation ? t('no_forecast_desc') : t('no_station');
    return (
      <section className="flex shrink-0 items-center gap-5 rounded-xl border border-line bg-white px-5 py-4 shadow-sm">
        <span className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-slate-100">
          <HourglassIcon className="h-11 w-11 text-slate-400" aria-hidden="true" />
        </span>
        <div>
          <p className="text-[20px] font-bold text-ink">{t('no_forecast_title')}</p>
          <p className="text-[14px] text-slate-600">{message}</p>
        </div>
      </section>
    );
  }

  const ui = alertUi(prediction.alert_level);
  const tone = TONE_CLASS[ui?.tone ?? 'muted'];
  const Icon = ui?.icon ?? HourglassIcon;
  const reserve = prediction.reserve_kw ?? prediction.delta_p_kw;

  return (
    <section
      role="status"
      aria-live="polite"
      className={`flex shrink-0 flex-wrap items-center gap-5 rounded-xl border px-5 py-4 shadow-sm ${tone.box}`}
    >
      <span className="flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full bg-white/80">
        <Icon className={`h-12 w-12 ${tone.icon}`} strokeWidth={2} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1 basis-[320px]">
        <p className="text-[12.5px] font-semibold text-slate-600">{selectedStation?.name ?? prediction.station_name}</p>
        <p className="text-[22px] font-bold leading-tight text-ink">{ui ? t(ui.labelKey) : prediction.alert_level}</p>
        <p className="mt-1 text-[14.5px] leading-snug text-slate-800">{prediction.recommendation_text}</p>
      </div>
      {!prediction.is_night && (
        <dl className="flex shrink-0 gap-6 text-right">
          <div>
            <dt className="text-[12.5px] font-medium text-slate-600">{t('hero_shortfall')}</dt>
            <dd className="text-[24px] font-bold leading-tight text-ink tabular-nums">
              {kw(prediction.delta_p_kw)} <span className="text-[14px] font-medium text-slate-600">kW</span>
            </dd>
          </div>
          <div>
            <dt className="text-[12.5px] font-medium text-slate-600">{t('hero_reserve')}</dt>
            <dd className="text-[24px] font-bold leading-tight text-ink tabular-nums">
              {kw(reserve)} <span className="text-[14px] font-medium text-slate-600">kW</span>
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}
