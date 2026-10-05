/**
 * Labeling API client — ground-truth GHI (เครื่องวัดจริง) สำหรับ retrain LSTM.
 * ตรงกับ backend: api/label_studio/schema.py และ api/inference/schema.py
 */
import { API_BASE_URL } from '@/lib/config';
import { apiFetch, getAuthHeaders } from './api';

export interface AlignedForecastPoint {
  timestamp: string; // ISO (UTC) ช่อง 10 นาที
  /** Final forecast (LSTM blended with the satellite cloud forecast) */
  predicted_ghi: number | null;
  /** LSTM-only forecast of the same run */
  predicted_ghi_lstm: number | null;
  weather_ghi: number | null;
  label_ghi: number | null;
}

export interface PredictionsByDateResponse {
  station_id: string;
  date: string;
  prediction_runs: number;
  label_count: number;
  matched_label_count: number;
  mae_vs_label: number | null;
  mae_lstm_vs_label: number | null;
  label_error: string | null;
  points: AlignedForecastPoint[];
}

export interface GroundTruthItem {
  timestamp: string; // ISO-8601 ; ไม่มี timezone = เวลาไทย
  ghi_actual: number;
}

export interface BatchSubmitResponse {
  station_id: string;
  received: number;
  created: number;
  updated: number;
  unchanged: number;
  rejected: { index: number; reason: string }[];
  retrain_enqueued: boolean;
  retrain_status: string;
}

export interface UploadPreviewResponse {
  filename: string;
  headers: string[];
  guessed_timestamp: string | null;
  guessed_ghi: string | null;
  sample_rows: string[][];
  total_rows: number;
}

export interface UploadGroundTruthResponse extends BatchSubmitResponse {
  filename: string;
  date: string;
  total_rows: number;
  invalid_rows: number;
  outside_day: number;
  duplicates_collapsed: number;
  clamped_negative: number;
}

export class LabelingApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function send<T>(path: string, init: RequestInit, json: boolean): Promise<T> {
  const headers: Record<string, string> = { ...getAuthHeaders() };
  // multipart (FormData): ห้ามใส่ Content-Type เอง ให้ browser ใส่ boundary
  if (json) headers['Content-Type'] = 'application/json';
  const res = await apiFetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: 'no-store' });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new LabelingApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const labelingApi = {
  getPredictionsByDate(stationId: string, date: string): Promise<PredictionsByDateResponse> {
    const q = new URLSearchParams({ station_id: stationId, date });
    return send(`/api/inference/predictions-by-date?${q.toString()}`, { method: 'GET' }, true);
  },

  submitBatch(stationId: string, items: GroundTruthItem[]): Promise<BatchSubmitResponse> {
    return send(
      '/api/label-studio/ground-truth/batch-submit',
      { method: 'POST', body: JSON.stringify({ station_id: stationId, items, source: 'manual' }) },
      true,
    );
  },

  previewFile(file: File): Promise<UploadPreviewResponse> {
    const form = new FormData();
    form.append('file', file);
    return send('/api/label-studio/ground-truth/upload/preview', { method: 'POST', body: form }, false);
  },

  uploadFile(
    stationId: string,
    date: string,
    timestampCol: string,
    ghiCol: string,
    file: File,
  ): Promise<UploadGroundTruthResponse> {
    const form = new FormData();
    form.append('station_id', stationId);
    form.append('date', date);
    form.append('timestamp_col', timestampCol);
    form.append('ghi_col', ghiCol);
    form.append('file', file);
    return send('/api/label-studio/ground-truth/upload', { method: 'POST', body: form }, false);
  },
};
