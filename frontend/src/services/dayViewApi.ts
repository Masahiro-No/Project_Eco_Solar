/**
 * Whole-day views: forecasts of a day at a chosen lead time, the satellite frames of a day,
 * the weather values fed to the LSTM and the retrain state of both models.
 * Matches backend: api/inference (predictions-by-date), api/ingestion (day-frames, weather recent), api/retrain.
 */
import { send } from './labelingApi';

export interface DayViewPoint {
  timestamp: string; // 10-minute slot, ISO (UTC)
  weather_ghi: number | null;
  label_ghi: number | null;
  clearsky_ghi: number | null;
  /** past slots: forecast made `lead_minutes` earlier; future slots: the newest forecast */
  forecast_ghi: number | null;
  forecast_ghi_lstm: number | null;
  forecast_lead_minutes: number | null;
  forecast_target_kw: number | null;
  forecast_cloud_pct: number | null;
  forecast_sat_loss_pct: number | null;
}

export interface DayViewResponse {
  station_id: string;
  date: string;
  prediction_runs: number;
  label_count: number;
  label_error: string | null;
  lead_minutes: number | null;
  view_matched_label_count: number;
  view_mae_vs_label: number | null;
  view_mae_lstm_vs_label: number | null;
  points: DayViewPoint[];
}

export interface DayFrame {
  timestamp: string;
  cloud_pct: number | null;
  image_b64: string;
}

export interface ForecastFrame extends DayFrame {
  lead_minutes: number;
}

export interface DayFramesResponse {
  station_id: string;
  date: string;
  frames: DayFrame[];
  night_frames: number;
  blank_frames: number;
  forecast: {
    end_time: string | null;
    created_at: string | null;
    status: string;
    reason: string | null;
    model_version: string | null;
    frames: ForecastFrame[];
  } | null;
}

export interface WeatherRow {
  timestamp: string;
  temperature: number;
  relative_humidity: number;
  ghi: number;
  dni: number;
  dhi: number | null;
  clearsky_ghi: number;
  solar_zenith_angle: number;
  wind_speed: number;
  surface_pressure: number | null;
  cloud_cover: number;
  source: string;
}

export interface RetrainRun {
  run_id: string;
  /** true when the run logged one value per epoch (runs before 5 Oct 2026 evening did not) */
  has_curves: boolean;
  started_at: string;
  outcome: string; // deployed | rejected | unknown
  reason: string | null;
  version: string | null;
  gate: string; // measured_ghi | weather_only | val_mse
  metric: string; // real_mae | val_mae | val_mse
  before: number | null;
  after: number | null;
  details: Record<string, string | number | null>;
}

export interface RetrainStatus {
  retrain_enabled: boolean;
  lstm: {
    model_version: string | null;
    trained_at: string | null;
    lookback_steps: number | null;
    previous_version: string | null;
    scheduled: boolean;
    running: boolean;
  };
  convlstm: {
    model_version: string | null;
    retrained_at: string | null;
    new_scans: number | null;
    batch_size: number | null;
    newest_scan: string | null;
    checked_at: string | null;
    scheduled: boolean;
    running: boolean;
    rejected_frames_total: number;
  };
  history: { lstm: RetrainRun[]; convlstm: RetrainRun[] };
  history_error: string | null;
}

/** Learning curves of one retrain run: metric name -> value per epoch (epoch 0 = the model before the run). */
export interface RunCurves {
  run_id: string;
  curves: Record<string, { epoch: number; value: number }[]>;
}

/** Has the satellite-to-irradiance relation been compared with measured GHI of a station? */
export interface CalibrationStatus {
  station_id: string;
  state: 'fitted' | 'checked' | 'insufficient' | 'not_checked' | 'no_calibration';
  pairs: number | null;
  min_pairs: number;
  mae: number | null;
  checked_at: string | null;
  pending: boolean;
}

export const LEAD_OPTIONS = [10, 60, 120, 180] as const;
export type LeadMinutes = (typeof LEAD_OPTIONS)[number];

export const dayViewApi = {
  getDayView(stationId: string, date: string, leadMinutes: number): Promise<DayViewResponse> {
    const q = new URLSearchParams({ station_id: stationId, date, lead_minutes: String(leadMinutes) });
    return send(`/api/inference/predictions-by-date?${q.toString()}`, { method: 'GET' }, true);
  },

  getDayFrames(stationId: string, date: string): Promise<DayFramesResponse> {
    const q = new URLSearchParams({ date });
    return send(`/api/ingestion/satellite/${encodeURIComponent(stationId)}/day-frames?${q.toString()}`, { method: 'GET' }, true);
  },

  getRecentWeather(stationId: string, hours = 30): Promise<WeatherRow[]> {
    return send(`/api/ingestion/weather/${encodeURIComponent(stationId)}/recent?hours=${hours}`, { method: 'GET' }, true);
  },

  getRetrainStatus(): Promise<RetrainStatus> {
    return send('/api/retrain/status', { method: 'GET' }, true);
  },

  getRunCurves(runId: string): Promise<RunCurves> {
    return send(`/api/retrain/runs/${encodeURIComponent(runId)}/curves`, { method: 'GET' }, true);
  },

  getCalibrationStatus(stationId: string): Promise<CalibrationStatus> {
    return send(`/api/label-studio/ground-truth/calibration-status?station_id=${encodeURIComponent(stationId)}`, { method: 'GET' }, true);
  },
};

const TH_OFFSET_MS = 7 * 3600 * 1000;

/** Today's date in Thailand, YYYY-MM-DD. */
export const todayThai = () => new Date(Date.now() + TH_OFFSET_MS).toISOString().slice(0, 10);

/** HH:mm in Thailand time. */
export const hhmmThai = (ms: number) => {
  const d = new Date(ms + TH_OFFSET_MS);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
};

/** UTC milliseconds of a wall-clock time on a Thai day. */
export const thaiDayMs = (date: string, hour: number, minute = 0) =>
  Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)), hour, minute) - TH_OFFSET_MS;

/** 'YYYY-MM-DD HH:MM:SS UTC' or ISO text from the backend -> 'DD/MM HH:mm' in Thailand time; the text itself when unparseable. */
export function thaiDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const ms = Date.parse(value.replace(' UTC', 'Z').replace(' ', 'T'));
  if (Number.isNaN(ms)) return value;
  const d = new Date(ms + TH_OFFSET_MS);
  return `${String(d.getUTCDate()).padStart(2, '0')}/${String(d.getUTCMonth() + 1).padStart(2, '0')} ${hhmmThai(ms)}`;
}
