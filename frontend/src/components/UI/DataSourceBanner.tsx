"use client";

import React from 'react';
import { AlertTriangleIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useForecast } from '@/context/ForecastContext';

/** Warns the operator when the dashboard is NOT showing live backend data. */
export function DataSourceBanner() {
  const t = useTranslations('common');
  const { isLive, isLoading } = useForecast();

  if (isLive || isLoading) return null;

  return (
    <div
      role="alert"
      className="flex shrink-0 items-start gap-2.5 rounded-lg border border-warn/30 bg-warn-soft px-3.5 py-2.5 text-warn"
    >
      <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="text-[12.5px] leading-snug">
        <span className="font-bold">{t('data_source_banner_title')}</span>
        <span className="text-slate-700"> — {t('data_source_banner_desc')}</span>
      </div>
    </div>
  );
}
