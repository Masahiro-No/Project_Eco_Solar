"use client";

import React, { useEffect, useState } from 'react';
import { ClockIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useForecast } from '@/context/ForecastContext';
import { forecastTimeLabel, parseBackendDate } from '@/lib/time';

/** A prediction is expected every 10 minutes; warn when it is clearly overdue. */
const STALE_AFTER_MIN = 25;

export function ForecastFreshness() {
  const t = useTranslations('common');
  const { isLive, prediction, lastUpdated } = useForecast();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const produced = parseBackendDate(lastUpdated);
  if (!isLive || !produced) return null;

  const ageMin = Math.max(0, Math.floor((now - produced.getTime()) / 60_000));
  const stale = ageMin > STALE_AFTER_MIN;
  // forecastTimeLabel(x, 0) = x snapped to the model grid, formatted HH:mm (Thailand time)
  const runLabel = forecastTimeLabel(prediction?.data_time || lastUpdated, 0);

  return (
    <div
      role="status"
      className={`ml-auto flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-[12px] font-medium ${
        stale ? 'border-warn/40 bg-warn-soft text-warn' : 'border-line bg-white text-slate-600'
      }`}
    >
      <ClockIcon className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{t('forecast_updated', { time: runLabel, minutes: ageMin })}</span>
      {stale && <span className="font-bold">· {t('forecast_stale')}</span>}
    </div>
  );
}
