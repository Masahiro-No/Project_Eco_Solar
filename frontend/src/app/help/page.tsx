"use client";

import React from 'react';
import { BookOpenIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { ALERT_UI, CLOUD_UI, TONE_CLASS } from '@/lib/levels';

type TermKey = 'help_ghi' | 'help_pgen' | 'help_ptarget' | 'help_dp' | 'help_reserve' | 'help_ghi_blend' | 'help_cloud' | 'help_lstm' | 'help_convlstm' | 'help_band';

const TERMS: { term: string; key: TermKey }[] = [
  { term: 'GHI', key: 'help_ghi' },
  { term: 'P_gen', key: 'help_pgen' },
  { term: 'P_target', key: 'help_ptarget' },
  { term: 'ΔP', key: 'help_dp' },
  { term: 'Reserve', key: 'help_reserve' },
  { term: 'LSTM', key: 'help_lstm' },
  { term: 'ConvLSTM', key: 'help_convlstm' },
  { term: 'GHI (blend)', key: 'help_ghi_blend' },
  { term: 'Cloud cover', key: 'help_cloud' },
  { term: '± RMSE', key: 'help_band' },
];

type AlertDescKey = 'help_alert_night' | 'help_alert_normal' | 'help_alert_watch' | 'help_alert_warning' | 'help_alert_critical';

/** Guide to the abbreviations, alert levels and cloud levels used across the app. */
export default function HelpPage() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 pb-4 text-ink">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
          <BookOpenIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('help_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('help_desc')}</p>
        </div>
      </div>

      <Panel title={t('help_terms_title')} icon={<BookOpenIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        <dl className="divide-y divide-line">
          {TERMS.map(({ term, key }) => (
            <div key={term} className="grid grid-cols-[130px_1fr] gap-3 py-2 text-[13.5px]">
              <dt className="font-bold text-ink">{term}</dt>
              <dd className="leading-snug text-slate-700">{t(key)}</dd>
            </div>
          ))}
        </dl>
      </Panel>

      <Panel title={t('help_alerts_title')} icon={<BookOpenIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {(Object.keys(ALERT_UI) as (keyof typeof ALERT_UI)[]).map((level) => {
            const ui = ALERT_UI[level];
            const Icon = ui.icon;
            return (
              <li key={level} className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${TONE_CLASS[ui.tone].box}`}>
                <Icon className={`h-9 w-9 shrink-0 ${TONE_CLASS[ui.tone].icon}`} aria-hidden="true" />
                <div>
                  <p className="text-[14px] font-bold text-ink">{t(ui.labelKey)}</p>
                  <p className="text-[12.5px] leading-snug text-slate-700">{t(`help_alert_${level}` as AlertDescKey)}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel title={t('help_cloud_title')} icon={<BookOpenIcon className="h-5 w-5 text-brand" />} className="shrink-0">
        <p className="mb-2 text-[13px] leading-snug text-slate-700">{t('help_cloud_method')}</p>
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-3">
          {(['low', 'medium', 'high'] as const).map((level) => {
            const ui = CLOUD_UI[level];
            const Icon = ui.icon;
            const loss = level === 'low' ? t('help_loss_low') : level === 'medium' ? t('help_loss_medium') : t('help_loss_high');
            return (
              <li key={level} className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${TONE_CLASS[ui.tone].box}`}>
                <Icon className={`h-9 w-9 shrink-0 ${TONE_CLASS[ui.tone].icon}`} aria-hidden="true" />
                <div>
                  <p className="text-[14px] font-bold text-ink">
                    {t(ui.labelKey)}
                  </p>
                  <p className="text-[12.5px] text-slate-700">{loss}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}
