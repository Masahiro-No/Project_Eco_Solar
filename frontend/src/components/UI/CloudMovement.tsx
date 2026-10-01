"use client";

import React from 'react';
import { CloudIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { cloudClasses } from '@/data/dashboard';

const toneStyles = {
  ok: { box: 'border-ok/40 bg-ok-soft', text: 'text-ok' },
  brand: { box: 'border-brand-mid bg-brand-soft ring-1 ring-brand-mid', text: 'text-brand' },
  warn: { box: 'border-warn/40 bg-warn-soft', text: 'text-warn' },
  muted: { box: 'border-slate-200 bg-slate-50', text: 'text-slate-600' },
};

const cloudDescMap: Record<string, string> = {
  clear: 'cloud_clear',
  inward: 'cloud_inward',
  outward: 'cloud_outward',
  overcast: 'cloud_overcast',
};

export function CloudMovement() {
  const t = useTranslations('common');
  const top = cloudClasses.reduce((a, b) => (b.pct > a.pct ? b : a));

  return (
    <Panel
      title={t('cloud_prediction_title')}
      icon={<CloudIcon className="h-5 w-5 text-slate-700" />}
      className="h-full"
    >
      <div className="grid min-h-0 flex-1 grid-cols-[1.3fr_1fr] gap-4">
        <div className="flex flex-col">
          <div className="flex items-stretch gap-3">
            <div className="flex flex-1 items-center overflow-hidden rounded-lg bg-brand-soft">
              <span className="flex h-full w-14 items-center justify-center bg-[#d7e5fb]">
                <CloudIcon className="h-8 w-8 text-[#1e3a8a]" strokeWidth={1.8} />
              </span>
              <div className="px-3 py-2">
                <p className="text-[21px] font-bold leading-tight text-[#1e3a8a]">{top.name}</p>
                <p className="text-[13px] font-semibold text-[#1e3a8a]">
                  {t(cloudDescMap[top.id] as any)}
                </p>
              </div>
            </div>
            <div className="flex w-[100px] flex-col justify-center">
              <p className="text-[12px] font-medium text-slate-600">{t('cloud_confidence')}</p>
              <p className="text-[22px] font-bold leading-tight text-ink">{top.pct}%</p>
              <div
                className="mt-1 h-2 rounded-full bg-slate-100"
                role="progressbar"
                aria-valuenow={top.pct}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="h-2 rounded-full bg-ok" style={{ width: `${top.pct}%` }} />
              </div>
            </div>
          </div>
          <p className="mb-1.5 mt-auto pt-2 text-[13px] font-semibold text-ink">
            {t('cloud_4_classes')}
          </p>
          <div className="grid grid-cols-4 gap-1.5">
            {cloudClasses.map((c) => {
              const s = toneStyles[c.tone];
              return (
                <div key={c.id} className={`rounded-lg border px-1.5 py-2 text-center ${s.box}`}>
                  <p className={`text-[12px] font-bold ${c.tone === 'muted' ? 'text-ink' : s.text}`}>
                    {c.name}
                  </p>
                  <p className={`truncate text-[10.5px] font-medium ${s.text}`}>
                    {t(cloudDescMap[c.id] as any)}
                  </p>
                  <p className={`mt-0.5 text-[13px] font-bold ${s.text}`}>{c.pct}%</p>
                </div>
              );
            })}
          </div>
        </div>
        <figure className="flex min-h-0 flex-col">
          <figcaption className="mb-1.5 text-[12px] font-semibold text-ink">
            {t('satellite_himawari')}
          </figcaption>
          <img
            src="/2de8a7c6-3c78-4961-9471-af149bf0e789.jpg"
            alt="Himawari satellite image of cloud cover over Southeast Asia"
            className="min-h-0 w-full flex-1 rounded-lg object-cover"
          />
          <p className="mt-1.5 text-[11px] font-medium text-muted">
            {t('latest_frame')}
          </p>
        </figure>
      </div>
    </Panel>
  );
}