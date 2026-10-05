"use client";

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCheckIcon, ClipboardCheckIcon, FileUpIcon, RefreshCwIcon, SaveIcon } from 'lucide-react';
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Panel } from '@/components/UI/Panel';
import { useAuth } from '@/context/AuthContext';
import { solarApi, StationResponse } from '@/services/api';
import {
  BatchSubmitResponse,
  GroundTruthItem,
  LabelingApiError,
  PredictionsByDateResponse,
  UploadGroundTruthResponse,
  UploadPreviewResponse,
  labelingApi,
} from '@/services/labelingApi';

const TH_OFFSET_MS = 7 * 3600 * 1000;
const MAX_GHI = 1500;

const todayThai = () => new Date(Date.now() + TH_OFFSET_MS).toISOString().slice(0, 10);
const hhmm = (ms: number) => {
  const d = new Date(ms + TH_OFFSET_MS);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
};
const r1 = (v: number | null | undefined) => (v === null || v === undefined ? null : Math.round(v * 10) / 10);
const show = (v: number | null | undefined) => (v === null || v === undefined ? '—' : v.toFixed(1));

interface Row {
  ms: number;
  pred: number | null; // ค่าพยากรณ์สุดท้าย (LSTM รวมกับภาพดาวเทียม)
  lstm: number | null; // LSTM อย่างเดียว
  weather: number | null;
  saved: number | null; // label ที่บันทึกไว้แล้วใน Label Studio
}

type Result = BatchSubmitResponse | UploadGroundTruthResponse;
const isFileResult = (r: Result): r is UploadGroundTruthResponse => 'total_rows' in r;

export default function LabelingPage() {
  const t = useTranslations('common');
  const [stations, setStations] = useState<StationResponse[]>([]);
  const [stationId, setStationId] = useState('');
  const [date, setDate] = useState(todayThai());
  const [mode, setMode] = useState<'edit' | 'file'>('edit');

  const [data, setData] = useState<PredictionsByDateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [values, setValues] = useState<Record<number, string>>({}); // ค่าที่ผู้ใช้พิมพ์
  const [checked, setChecked] = useState<Record<number, boolean>>({}); // แถวที่จะบันทึก

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<UploadPreviewResponse | null>(null);
  const [tsCol, setTsCol] = useState('');
  const [ghiCol, setGhiCol] = useState('');

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needLogin, setNeedLogin] = useState(false); // token หาย/หมดอายุ (API ตอบ 401)

  const router = useRouter();
  const { logout, isAdmin } = useAuth();

  const handleError = useCallback(
    (e: unknown) => {
      if (e instanceof LabelingApiError && e.status === 401) {
        setNeedLogin(true);
        setError(t('lb_login_required'));
      } else setError(`${t('lb_error')}: ${e instanceof Error ? e.message : String(e)}`);
    },
    [t],
  );

  // ต้อง logout ก่อน ไม่งั้นหน้า /login เห็นว่ายังล็อกอินอยู่แล้วเด้งกลับ
  const relogin = () => {
    logout();
    router.push('/login');
  };

  const load = useCallback(async () => {
    if (!stationId) return;
    setLoading(true);
    setError(null);
    try {
      setData(await labelingApi.getPredictionsByDate(stationId, date));
      setValues({});
      setChecked({});
    } catch (e) {
      setData(null);
      handleError(e);
    } finally {
      setLoading(false);
    }
  }, [stationId, date, handleError]);

  useEffect(() => {
    solarApi.getStations().then((s) => {
      setStations(s);
      if (s.length) setStationId((cur) => cur || s[0].id);
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows: Row[] = useMemo(
    () =>
      (data?.points ?? []).map((p) => ({
        ms: new Date(p.timestamp).getTime(),
        pred: r1(p.predicted_ghi),
        lstm: r1(p.predicted_ghi_lstm),
        weather: r1(p.weather_ghi),
        saved: r1(p.label_ghi),
      })),
    [data],
  );

  // ค่าในช่อง input: ที่ผู้ใช้พิมพ์ > label ที่บันทึกไว้ > ค่าทำนาย (default)
  const cellValue = (r: Row) => values[r.ms] ?? (r.saved ?? r.pred ?? '').toString();
  const numeric = (s: string) => (s.trim() === '' ? NaN : Number(s));
  const valid = (s: string) => Number.isFinite(numeric(s)) && numeric(s) >= 0 && numeric(s) <= MAX_GHI;

  const toSave = rows.filter((r) => checked[r.ms] && valid(cellValue(r)));
  const invalidChecked = rows.filter((r) => checked[r.ms] && !valid(cellValue(r))).length;

  const chartData = rows.map((r) => ({
    t: hhmm(r.ms),
    pred: r.pred,
    weather: r.weather,
    label: checked[r.ms] && valid(cellValue(r)) ? numeric(cellValue(r)) : r.saved,
  }));

  const confirmAllForecasts = () =>
    setChecked((c) => ({ ...c, ...Object.fromEntries(rows.filter((r) => r.saved === null && r.pred !== null).map((r) => [r.ms, true])) }));

  const saveEdits = async () => {
    if (!stationId || toSave.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const items: GroundTruthItem[] = toSave.map((r) => ({ timestamp: new Date(r.ms).toISOString(), ghi_actual: numeric(cellValue(r)) }));
      setResult(await labelingApi.submitBatch(stationId, items));
      await load();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const pickFile = async (f: File | undefined) => {
    setFile(f ?? null);
    setPreview(null);
    setResult(null);
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const p = await labelingApi.previewFile(f);
      setPreview(p);
      setTsCol(p.guessed_timestamp ?? '');
      setGhiCol(p.guessed_ghi ?? '');
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const importFile = async () => {
    if (!file || !stationId || !tsCol || !ghiCol) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await labelingApi.uploadFile(stationId, date, tsCol, ghiCol, file));
      setFile(null);
      setPreview(null);
      await load();
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };

  const field = 'rounded-lg border border-line bg-white px-2.5 py-1.5 text-[13px] text-ink';
  const btn = 'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold disabled:opacity-40';
  const tab = (active: boolean) =>
    `rounded-lg px-3.5 py-1.5 text-[13px] font-semibold ${active ? 'bg-brand text-white' : 'bg-white text-slate-700 border border-line hover:bg-canvas'}`;

  if (!isAdmin) {
    return (
      <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[14px] text-amber-800">
        {t('admin_only')}
      </div>
    );
  }

  return (
    // text-ink: ไม่งั้นข้อความที่ไม่กำหนดสีจะรับสี foreground ของ dark mode (#ededed) มาแสดงบนพื้นขาว
    <div className="flex min-w-0 flex-col gap-4 pb-4 text-ink">
      <div className="flex shrink-0 items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700">
          <ClipboardCheckIcon className="h-6 w-6" strokeWidth={2.2} />
        </span>
        <div>
          <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('lb_title')}</h1>
          <p className="text-[13.5px] text-slate-600">{t('lb_desc')}</p>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex shrink-0 flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          <span>{error}</span>
          {needLogin && (
            <button onClick={relogin} className="rounded-md bg-red-600 px-2.5 py-1 text-[12.5px] font-semibold text-white hover:bg-red-700">
              {t('lb_login_again')}
            </button>
          )}
        </div>
      )}
      {data?.label_error && (
        <div className="shrink-0 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
          {t('lb_label_error')}: {data.label_error}
        </div>
      )}

      <Panel
        className="shrink-0"
        title={t('lb_pick_title')}
        icon={<ClipboardCheckIcon className="h-5 w-5 text-brand" />}
        action={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <select aria-label={t('lb_station')} className={field} value={stationId} onChange={(e) => setStationId(e.target.value)}>
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} — {s.name}
                </option>
              ))}
            </select>
            <input aria-label={t('lb_date')} type="date" className={field} value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
            <button onClick={load} disabled={loading} className={`${btn} border border-line bg-white text-slate-700 hover:bg-canvas`}>
              <RefreshCwIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              {t('lb_load')}
            </button>
          </div>
        }
      >
        <p className="text-[12.5px] text-slate-600">
          {data ? (
            <>
              {t('lb_runs')}: <b>{data.prediction_runs}</b> · {t('lb_labeled')}: <b>{data.label_count}</b>
              {data.mae_vs_label !== null && (
                <>
                  {' '}
                  · {t('lb_mae')}: <b>{data.mae_vs_label}</b> W/m² ({data.matched_label_count})
                  {data.mae_lstm_vs_label !== null && (
                    <>
                      {' '}
                      · {t('lb_mae_lstm')}: <b>{data.mae_lstm_vs_label}</b> W/m²
                    </>
                  )}
                </>
              )}
            </>
          ) : (
            t('lb_no_data')
          )}
        </p>
        <p className="mt-1 text-[11.5px] text-muted">{t('lb_time_note')}</p>
      </Panel>

      <div className="flex shrink-0 gap-2">
        <button className={tab(mode === 'edit')} onClick={() => setMode('edit')}>
          {t('lb_tab_edit')}
        </button>
        <button className={tab(mode === 'file')} onClick={() => setMode('file')}>
          {t('lb_tab_file')}
        </button>
      </div>

      {mode === 'edit' && (
        <>
          <Panel className="shrink-0" title={t('lb_chart_title')} icon={<ClipboardCheckIcon className="h-5 w-5 text-brand" />}>
            {rows.length === 0 ? (
              <p className="py-8 text-center text-[13px] text-muted">{t('lb_no_points')}</p>
            ) : (
              <div className="h-[260px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
                    <CartesianGrid stroke="#eef2f7" />
                    <XAxis dataKey="t" tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={{ stroke: '#cbd5e1' }} minTickGap={24} />
                    <YAxis domain={[0, 'auto']} tick={{ fontSize: 11, fill: '#475569' }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ fontSize: 12.5, borderRadius: 8, borderColor: '#e3e9f2' }} />
                    <Line dataKey="weather" name={t('lb_legend_weather')} stroke="#94a3b8" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls />
                    <Line dataKey="pred" name={t('lb_legend_pred')} stroke="#3b82f6" strokeWidth={1.8} strokeDasharray="6 5" dot={false} isAnimationActive={false} connectNulls />
                    <Scatter dataKey="label" name={t('lb_legend_label')} fill="#16a34a" isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </Panel>

          <Panel
            className="shrink-0"
            title={t('lb_table_title')}
            icon={<CheckCheckIcon className="h-5 w-5 text-brand" />}
            action={
              <div className="flex flex-wrap items-center justify-end gap-2">
                <button onClick={confirmAllForecasts} disabled={rows.length === 0} className={`${btn} border border-line bg-white text-slate-700 hover:bg-canvas`} title={t('lb_confirm_all_hint')}>
                  <CheckCheckIcon className="h-3.5 w-3.5" />
                  {t('lb_confirm_all')}
                </button>
                <button onClick={() => setChecked({})} disabled={toSave.length + invalidChecked === 0} className={`${btn} border border-line bg-white text-slate-700 hover:bg-canvas`}>
                  {t('lb_clear')}
                </button>
                <button onClick={saveEdits} disabled={busy || toSave.length === 0} className={`${btn} bg-emerald-600 text-white`}>
                  <SaveIcon className="h-3.5 w-3.5" />
                  {busy ? t('lb_saving') : `${t('lb_save')} (${toSave.length})`}
                </button>
              </div>
            }
          >
            <p className="mb-2 text-[12px] text-muted">{t('lb_table_hint')}</p>
            {data?.prediction_runs === 0 && rows.length > 0 && <p className="mb-2 text-[12px] text-amber-700">{t('lb_no_runs')}</p>}
            {invalidChecked > 0 && <p className="mb-2 text-[12px] text-red-600">{t('lb_invalid_values', { n: invalidChecked, max: MAX_GHI })}</p>}
            <div className="max-h-[440px] overflow-auto rounded-lg border border-line">
              <table className="w-full text-left text-[13px]">
                <thead className="sticky top-0 border-b border-line bg-canvas font-bold text-slate-700">
                  <tr>
                    <th className="w-10 px-3 py-2 text-center" aria-label={t('lb_col_confirm')} />
                    <th className="px-3 py-2">{t('lb_col_time')}</th>
                    <th className="px-3 py-2 text-right">{t('lb_col_pred')}</th>
                    <th className="px-3 py-2 text-right">{t('lb_col_lstm')}</th>
                    <th className="px-3 py-2 text-right">{t('lb_col_weather')}</th>
                    <th className="px-3 py-2 text-right">{t('lb_col_label')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line bg-white">
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-6 text-center text-muted">
                        {t('lb_no_points')}
                      </td>
                    </tr>
                  )}
                  {rows.map((r) => {
                    const on = !!checked[r.ms];
                    const bad = on && !valid(cellValue(r));
                    return (
                      <tr key={r.ms} className={on ? 'bg-emerald-50/60' : r.saved !== null ? 'bg-slate-50/60' : ''}>
                        <td className="px-3 py-1.5 text-center">
                          <input type="checkbox" aria-label={`${t('lb_col_confirm')} ${hhmm(r.ms)}`} checked={on} onChange={(e) => setChecked((c) => ({ ...c, [r.ms]: e.target.checked }))} />
                        </td>
                        <td className="px-3 py-1.5 font-medium tabular-nums text-ink">
                          {hhmm(r.ms)}
                          {r.saved !== null && !on && <span className="ml-2 rounded-full bg-ok-soft px-1.5 py-0.5 text-[10.5px] font-bold text-ok">{t('lb_saved')}</span>}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{show(r.pred)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{show(r.lstm)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">{show(r.weather)}</td>
                        <td className="px-3 py-1.5 text-right">
                          <input
                            aria-label={`${t('lb_col_label')} ${hhmm(r.ms)}`}
                            type="number"
                            min={0}
                            max={MAX_GHI}
                            step="any"
                            value={cellValue(r)}
                            onChange={(e) => {
                              const v = e.target.value;
                              setValues((cur) => ({ ...cur, [r.ms]: v }));
                              setChecked((c) => ({ ...c, [r.ms]: true })); // แก้ค่า = ยืนยันแถวนั้นอัตโนมัติ
                            }}
                            className={`w-24 rounded border px-2 py-1 text-right text-[13px] tabular-nums ${bad ? 'border-red-400 bg-red-50' : 'border-line bg-white'}`}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}

      {mode === 'file' && (
        <Panel className="shrink-0" title={t('lb_file_title')} icon={<FileUpIcon className="h-5 w-5 text-brand" />}>
          <p className="mb-3 text-[12.5px] text-slate-600">{t('lb_file_hint', { date })}</p>
          <div className="flex flex-wrap items-center gap-3">
            <label className={`${btn} cursor-pointer border border-line bg-white text-slate-700 hover:bg-canvas`}>
              <FileUpIcon className="h-3.5 w-3.5" />
              {t('lb_file_choose')}
              <input
                type="file"
                accept=".csv,.xlsx,.xlsm,text/csv"
                className="sr-only"
                onChange={(e) => {
                  pickFile(e.target.files?.[0]);
                  e.target.value = '';
                }}
              />
            </label>
            {file && (
              <span className="min-w-0 truncate text-[12.5px] text-slate-600">
                {file.name} · {(file.size / 1024).toFixed(1)} KB
              </span>
            )}
          </div>

          {preview && (
            <div className="mt-4 flex flex-col gap-3">
              <div className="flex flex-wrap items-end gap-4">
                <label className="flex flex-col gap-1 text-[12px] font-semibold text-slate-700">
                  {t('lb_col_ts')}
                  <select className={field} value={tsCol} onChange={(e) => setTsCol(e.target.value)}>
                    <option value="">—</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-[12px] font-semibold text-slate-700">
                  {t('lb_col_ghi')}
                  <select className={field} value={ghiCol} onChange={(e) => setGhiCol(e.target.value)}>
                    <option value="">—</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="pb-2 text-[12px] text-muted">
                  {t('lb_file_rows')}: <b>{preview.total_rows}</b>
                </span>
                <button onClick={importFile} disabled={busy || !tsCol || !ghiCol || tsCol === ghiCol} className={`${btn} ml-auto bg-emerald-600 text-white`}>
                  <SaveIcon className="h-3.5 w-3.5" />
                  {busy ? t('lb_saving') : t('lb_import')}
                </button>
              </div>

              <div className="max-h-[220px] overflow-auto rounded-lg border border-line">
                <table className="w-full text-left text-[12.5px]">
                  <thead className="sticky top-0 border-b border-line bg-canvas font-bold text-slate-700">
                    <tr>
                      {preview.headers.map((h) => (
                        <th key={h} className={`whitespace-nowrap px-3 py-2 ${h === tsCol || h === ghiCol ? 'bg-brand-soft text-brand' : ''}`}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line bg-white">
                    {preview.sample_rows.map((row, i) => (
                      <tr key={i}>
                        {preview.headers.map((h, j) => (
                          <td key={h} className={`whitespace-nowrap px-3 py-1.5 ${h === tsCol || h === ghiCol ? 'bg-brand-soft/40 font-medium' : 'text-slate-600'}`}>
                            {row[j] ?? ''}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Panel>
      )}

      {result && (
        <Panel className="shrink-0" title={t('lb_result_title')} icon={<SaveIcon className="h-5 w-5 text-brand" />}>
          <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] text-slate-700 md:grid-cols-3">
            <li>
              {t('lb_created')}: <b>{result.created}</b>
            </li>
            <li>
              {t('lb_updated')}: <b>{result.updated}</b>
            </li>
            <li>
              {t('lb_unchanged')}: <b>{result.unchanged}</b>
            </li>
            <li>
              {t('lb_rejected')}: <b className={result.rejected.length ? 'text-red-600' : ''}>{result.rejected.length}</b>
            </li>
            {isFileResult(result) && (
              <>
                <li>
                  {t('lb_file_rows')}: <b>{result.total_rows}</b>
                </li>
                <li>
                  {t('lb_dup')}: <b>{result.duplicates_collapsed}</b>
                </li>
                <li>
                  {t('lb_clamped')}: <b>{result.clamped_negative}</b>
                </li>
                <li>
                  {t('lb_outside')}: <b>{result.outside_day}</b>
                </li>
                <li>
                  {t('lb_invalid_rows')}: <b>{result.invalid_rows}</b>
                </li>
              </>
            )}
            <li className="col-span-2 md:col-span-3">
              {t('lb_retrain')}: <b>{result.retrain_status}</b>
            </li>
          </ul>
          {result.rejected.length > 0 && (
            <p className="mt-2 text-[12px] text-red-600">
              {result.rejected.slice(0, 5).map((r) => `#${r.index + 1}: ${r.reason}`).join(' · ')}
              {result.rejected.length > 5 ? ' …' : ''}
            </p>
          )}
        </Panel>
      )}
    </div>
  );
}
