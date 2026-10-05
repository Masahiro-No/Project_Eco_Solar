"use client";

import React from 'react';
import { LightbulbIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { InfoTip } from './InfoTip';
import { useForecast } from '@/context/ForecastContext';
import { CLOUD_UI, alertUi } from '@/lib/levels';

const kw = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v).toLocaleString()} kW`);

type CloudCol = 'low' | 'medium' | 'high';
type CellKey = 'alert_normal' | 'alert_watch' | 'alert_warning' | 'alert_critical';

// The rule matrix of the decision engine (service/workers/decision.py)
const MATRIX: Record<'met' | 'short', Record<CloudCol, CellKey>> = {
  met: { low: 'alert_normal', medium: 'alert_watch', high: 'alert_warning' },
  short: { low: 'alert_warning', medium: 'alert_warning', high: 'alert_critical' },
};

/** Why the system recommends what it recommends: the inputs and the rule that fired. */
export function DecisionSupport() {
  const t = useTranslations('common');
  const { prediction } = useForecast();

  if (!prediction) {
    return (
      <Panel title={t('decision_support_title')} icon={<LightbulbIcon className="h-5 w-5 text-slate-700" />} className="h-full">
        <p className="flex flex-1 items-center justify-center py-6 text-[13px] text-muted">{t('no_forecast_title')}</p>
      </Panel>
    );
  }

  const night = !!prediction.is_night;
  const row: 'met' | 'short' = prediction.delta_p_kw > 0 ? 'short' : 'met';
  const col = prediction.cloud_impact_level ?? null;
  const ui = alertUi(prediction.alert_level);

  const facts = [
    { label: t('kpi_pgen'), value: kw(prediction.estimated_power_kw), help: t('help_pgen') },
    { label: t('kpi_ptarget'), value: kw(prediction.target_power_kw), help: t('help_ptarget') },
    { label: t('kpi_dp'), value: kw(prediction.delta_p_kw), help: t('help_dp') },
    { label: t('hero_reserve'), value: kw(prediction.reserve_kw), help: t('help_reserve') },
  ];

  return (
    <Panel title={t('decision_support_title')} icon={<LightbulbIcon className="h-5 w-5 text-slate-700" />} className="h-full">
      <dl className="grid shrink-0 grid-cols-2 gap-2 lg:grid-cols-4">
        {facts.map((f) => (
          <div key={f.label} className="rounded-lg border border-line px-3 py-2">
            <dt className="flex items-center gap-1 text-[12px] font-medium text-slate-600">
              <span className="truncate">{f.label}</span>
              <InfoTip text={f.help} />
            </dt>
            <dd className="text-[18px] font-bold leading-tight text-ink tabular-nums">{f.value}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-[12.5px] font-bold text-ink">{t('rule_matrix_title')}</p>
      <div className="mt-1 overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-left text-[12.5px]">
          <thead className="bg-canvas text-slate-700">
            <tr>
              <th className="px-3 py-2 font-bold">{t('rule_power')}</th>
              {(['low', 'medium', 'high'] as const).map((c) => (
                <th key={c} className="px-3 py-2 font-bold">
                  {t(CLOUD_UI[c].labelKey)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {(['met', 'short'] as const).map((r) => (
              <tr key={r}>
                <th className="px-3 py-2 font-medium text-slate-700">{r === 'met' ? t('dp_met') : t('dp_short')}</th>
                {(['low', 'medium', 'high'] as const).map((c) => {
                  const active = !night && r === row && c === col;
                  return (
                    <td
                      key={c}
                      aria-current={active ? 'true' : undefined}
                      className={`px-3 py-2 ${active ? 'bg-brand-soft font-bold text-ink ring-2 ring-inset ring-brand-mid' : 'text-slate-600'}`}
                    >
                      {t(MATRIX[r][c])}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] leading-snug text-slate-600">
        {night
          ? t('rule_note_night')
          : col
          ? t('rule_note_now', { level: ui ? t(ui.labelKey) : prediction.alert_level })
          : t('rule_note_no_satellite')}
      </p>
    </Panel>
  );
}
