"use client";

import React, { useEffect, useState } from 'react';
import { SaveIcon, SettingsIcon, XIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { solarApi, StationPatchRequest } from '@/services/api';

export type StationSettingsTarget = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  panel_area: number;
  efficiency: number;
  target_capacity_kw: number;
  is_active: boolean;
};

const numberOf = (text: string) => (text.trim() === '' ? NaN : Number(text));

/**
 * Settings of one station: name, panel area, panel efficiency and the dispatch target.
 * An admin can change them; everyone else sees the values. The next forecast round uses what is saved here.
 */
export function StationSettings({ station, canEdit, onClose, onSaved }: {
  station: StationSettingsTarget;
  canEdit: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const t = useTranslations('common');
  const [name, setName] = useState(station.name);
  const [area, setArea] = useState(String(station.panel_area));
  const [effPct, setEffPct] = useState(String(Number((station.efficiency * 100).toFixed(2))));
  const [target, setTarget] = useState(String(station.target_capacity_kw));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const areaN = numberOf(area);
  const effN = numberOf(effPct) / 100;
  const targetN = numberOf(target);
  const problems = {
    name: name.trim() === '',
    area: !(areaN > 0),
    eff: !(effN > 0 && effN <= 1),
    target: !(targetN > 0),
  };
  const valid = !problems.name && !problems.area && !problems.eff && !problems.target;

  const changes: StationPatchRequest = {};
  if (name.trim() !== station.name) changes.name = name.trim();
  if (valid && areaN !== station.panel_area) changes.panel_area = areaN;
  if (valid && Math.abs(effN - station.efficiency) > 1e-9) changes.efficiency = effN;
  if (valid && targetN !== station.target_capacity_kw) changes.target_capacity_kw = targetN;
  const dirty = Object.keys(changes).length > 0;

  // output of the panels at 1000 W/m² (standard full sun), to judge whether the target is reachable
  const peakKw = valid ? areaN * effN : null;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canEdit || !valid || !dirty) return;
    setBusy(true);
    setError(null);
    const updated = await solarApi.patchStation(station.id, changes);
    setBusy(false);
    if (!updated) {
      setError(t('stc_save_failed'));
      return;
    }
    await onSaved();
    onClose();
  };

  const input = (bad: boolean) =>
    `mt-1 h-10 w-full rounded-lg border px-3 text-[14px] tabular-nums text-ink disabled:bg-slate-50 disabled:text-slate-700 ${bad ? 'border-red-400 bg-red-50' : 'border-line bg-white'}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="station-settings-title"
        className="w-full max-w-lg rounded-2xl bg-white p-6 text-ink shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand">
              <SettingsIcon className="h-5 w-5" />
            </span>
            <div>
              <h2 id="station-settings-title" className="text-[17px] font-bold text-ink">
                {t('stc_title')} <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[12.5px] text-brand">{station.id}</span>
              </h2>
              <p className="text-[12px] tabular-nums text-slate-600">
                {station.latitude.toFixed(4)}, {station.longitude.toFixed(4)} · {station.is_active ? t('online') : t('offline')}
              </p>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label={t('stc_close')} className="rounded-lg p-1 text-slate-500 hover:bg-slate-100">
            <XIcon className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={save} className="mt-4 flex flex-col gap-3.5 text-[13px] text-slate-700">
          <label>
            <span className="font-semibold text-ink">{t('th_station_name')}</span>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} disabled={!canEdit} maxLength={255} className={input(problems.name)} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label>
              <span className="font-semibold text-ink">{t('stc_area')}</span>
              <input type="number" min={0} step="any" inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)} disabled={!canEdit} className={input(problems.area)} />
            </label>
            <label>
              <span className="font-semibold text-ink">{t('stc_efficiency')}</span>
              <input type="number" min={0} max={100} step="any" inputMode="decimal" value={effPct} onChange={(e) => setEffPct(e.target.value)} disabled={!canEdit} className={input(problems.eff)} />
            </label>
          </div>
          <label>
            <span className="font-semibold text-ink">{t('stc_target')}</span>
            <input type="number" min={0} step="any" inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} disabled={!canEdit} className={input(problems.target)} />
          </label>

          <p className="rounded-lg bg-canvas px-3 py-2 text-[12.5px] leading-snug text-slate-700">
            {peakKw === null
              ? t('stc_invalid')
              : t('stc_peak', { peak: Math.round(peakKw).toLocaleString(), pct: targetN > 0 ? Math.round((targetN / peakKw) * 100) : 0 })}
            {peakKw !== null && targetN > peakKw ? ` ${t('stc_target_above_peak')}` : ''}
          </p>
          <p className="text-[12.5px] leading-snug text-slate-600">{canEdit ? t('stc_applies') : t('stc_readonly')}</p>

          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {error}
            </p>
          )}

          <div className="mt-1 flex items-center justify-end gap-2 border-t border-line pt-3">
            <button type="button" onClick={onClose} className="h-10 rounded-lg border border-line bg-white px-4 text-[13px] font-semibold text-slate-700 hover:bg-canvas">
              {t(canEdit ? 'stc_cancel' : 'stc_close')}
            </button>
            {canEdit && (
              <button
                type="submit"
                disabled={busy || !valid || !dirty}
                className="flex h-10 items-center gap-1.5 rounded-lg bg-brand px-4 text-[13px] font-bold text-white hover:bg-brand/90 disabled:opacity-40"
              >
                <SaveIcon className="h-4 w-4" />
                {t('stc_save')}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
