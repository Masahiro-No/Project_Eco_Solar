/**
 * SolarDSS API Client Service
 * Connects frontend with FastAPI Backend & AI Model Inference Engine.
 * Strictly aligned with Backend Pydantic Schemas in api/stations/schema.py
 * No mock data: when the backend has nothing, the functions return null / [] and the UI says so.
 */

import { API_BASE_URL } from '@/lib/config';

export function getAuthHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('solar_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Fired on window when the backend answers 401: the session is missing or expired. */
export const UNAUTHORIZED_EVENT = 'solar:unauthorized';

/** fetch() for backend calls: always sends the session token; a 401 tells the AuthProvider to end the session. */
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const headers = { ...getAuthHeaders(), ...(init?.headers as Record<string, string> | undefined) };
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return res;
}

// ==========================================
// Station API Schemas (api/stations/schema.py)
// ==========================================

export interface StationBase {
  name: string;
  latitude: number;
  longitude: number;
  panel_area: number; // Area in m^2
  efficiency: number; // 0.0 to 1.0 (e.g. 0.185)
  target_capacity_kw: number; // Target capacity in kW
}

export interface StationCreateRequest extends StationBase {
  id?: string; // Optional custom ID (e.g. "ST-001")
}

export type StationUpdateRequest = StationBase;

export interface StationPatchRequest {
  name?: string;
  latitude?: number;
  longitude?: number;
  panel_area?: number;
  efficiency?: number;
  target_capacity_kw?: number;
}

export interface StationResponse extends StationBase {
  id: string;
  is_active: boolean;
  deleted_at?: string | null;
  created_at?: string;
  updated_at?: string;
  current_pgen_kw?: number;
  alert_level?: string;
  province?: string;
}

// Backward-compatibility alias
export type StationDto = StationResponse;

export interface NearestStationResponse {
  station_id: string;
  name: string;
  latitude: number;
  longitude: number;
  target_capacity_kw: number;
  distance_km: number;
}

// ==========================================
// Inference API Schemas
// ==========================================

export type AlertLevel = 'night' | 'normal' | 'watch' | 'warning' | 'critical';
export type CloudImpactLevel = 'low' | 'medium' | 'high';
export type SatelliteStatus = 'ok' | 'shifted' | 'gap_skipped' | 'observed_only' | 'missing' | 'night' | 'low_sun' | 'model_unavailable';

export interface PredictionResultData {
  job_id: string;
  station_id: string;
  station_name: string;
  predicted_at: string;
  forecast_horizon_hours: number;
  /** Final GHI per 10-minute step: LSTM blended with the satellite cloud forecast */
  ghi_forecast_curve: number[];
  /** LSTM forecast before blending */
  ghi_forecast_lstm_raw?: number[] | null;
  /** Weight of the satellite branch per step (0 = LSTM only) */
  blend_weight?: number[] | null;
  /** Forecast cloud cover (%) in the area around the station; null where no satellite forecast covers the step */
  cloud_coverage_pct?: (number | null)[] | null;
  cloud_coverage_now_pct?: number | null;
  /** Expected loss of GHI (%) against clear sky per step, from the satellite branch */
  sat_ghi_loss_pct?: (number | null)[] | null;
  sat_ghi_loss_now_pct?: number | null;
  /** true = the satellite relation was fitted on measured GHI of this station */
  sat_calibration_verified?: boolean | null;
  /** when verified: fitted on this station, or the line of another station checked here (error in clear-sky index) */
  sat_calibration_check?: { fitted: boolean; pairs: number | null; mae: number | null } | null;
  /** Target per step: the smaller of P_target and a share of the clear-sky output at that time */
  target_profile_kw?: number[] | null;
  /** Typical error range of the GHI forecast: forecast -/+ the model's RMSE at that lead time */
  ghi_forecast_lower?: number[] | null;
  ghi_forecast_upper?: number[] | null;
  cloud_impact_level?: CloudImpactLevel | null;
  satellite_status?: SatelliteStatus | null;
  satellite_lag_minutes?: number | null;
  is_night?: boolean | null;
  /** P_gen at the first forecast step, from the blended GHI */
  estimated_power_kw: number;
  target_power_kw: number;
  /** Largest shortfall against the target in the horizon (0 if the target is met) */
  delta_p_kw: number;
  /** Recommended reserve: shortfall plus the forecast-uncertainty buffer */
  reserve_kw?: number | null;
  cloud_trend: string;
  alert_level: AlertLevel | string;
  recommendation_text: string;
  satellite_image_url?: string;
  model_version?: string | null;
  /** Timestamp of the newest weather observation the model was fed with */
  data_time?: string | null;
}

// ==========================================
// Dashboard API Schemas (api/dashboard/schema.py)
// ==========================================

export interface AlertFeedItem {
  station_id: string;
  station_name: string;
  alert_level: AlertLevel | string;
  event: string;
  delta_p_needed_kw: number;
  recommendation: string;
  timestamp: string;
}

// ==========================================
// API Client Service
// ==========================================

export const solarApi = {
  // ----------------------------------------
  // Stations API (api/stations/router.py)
  // ----------------------------------------

  /**
   * GET /api/stations - Fetch solar stations from Backend DB
   */
  async getStations(limit: number = 100, offset: number = 0, includeArchived: boolean = false): Promise<StationResponse[]> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations?limit=${limit}&offset=${offset}&include_archived=${includeArchived}`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          return data;
        }
      }
    } catch (err) {
      console.error('[solarApi.getStations] Backend request error:', err);
    }
    return [];
  },

  /**
   * GET /api/stations/archived - Fetch all soft-deleted stations from Backend DB
   */
  async getArchivedStations(): Promise<StationResponse[]> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/archived`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error('[solarApi.getArchivedStations] Backend error:', err);
    }
    return [];
  },

  /**
   * GET /api/stations/{station_id} - Fetch single station by ID from Backend DB
   */
  async getStationById(stationId: string): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/${stationId}`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.getStationById] Error fetching ${stationId}:`, err);
    }
    return null;
  },

  /**
   * POST /api/stations - Create a new solar station in Backend DB
   */
  async createStation(payload: StationCreateRequest): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error('[solarApi.createStation] Error creating station:', err);
    }
    return null;
  },

  /**
   * PUT /api/stations/{station_id} - Full update station spec in Backend DB
   */
  async updateStation(stationId: string, payload: StationUpdateRequest): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/${stationId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.updateStation] Error updating ${stationId}:`, err);
    }
    return null;
  },

  /**
   * PATCH /api/stations/{station_id} - Partial update station in Backend DB
   */
  async patchStation(stationId: string, payload: StationPatchRequest): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/${stationId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.patchStation] Error patching ${stationId}:`, err);
    }
    return null;
  },

  /**
   * DELETE /api/stations/{station_id} - Soft-delete station in Backend DB
   */
  async deleteStation(stationId: string): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/${stationId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.deleteStation] Error deleting ${stationId}:`, err);
    }
    return null;
  },

  /**
   * PATCH /api/stations/{station_id}/restore - Restore soft-deleted station in Backend DB
   */
  async restoreStation(stationId: string): Promise<StationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/${stationId}/restore`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.restoreStation] Error restoring ${stationId}:`, err);
    }
    return null;
  },

  /**
   * GET /api/stations/nearest - Find nearest station by coordinates in Backend DB
   */
  async findNearestStation(lat: number, lon: number): Promise<NearestStationResponse | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/stations/nearest?lat=${lat}&lon=${lon}`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error('[solarApi.findNearestStation] Error:', err);
    }
    return null;
  },

  // ----------------------------------------
  // Inference API (api/inference/router.py)
  // ----------------------------------------

  /**
   * Fetch the latest model forecast result for a given station
   */
  async getLatestPrediction(stationId: string = 'ST-001'): Promise<PredictionResultData | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/inference/latest/${stationId}`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info(`[solarApi.getLatestPrediction] Could not fetch live prediction for ${stationId}:`, err);
    }
    return null;
  },

  /**
   * Fetch historical prediction results for chart comparison
   */
  async getPredictionHistory(stationId: string = 'ST-001', limit: number = 20): Promise<PredictionResultData[]> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/inference/history/${stationId}?limit=${limit}`, {
        method: 'GET',
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info(`[solarApi.getPredictionHistory] Could not fetch history for ${stationId}:`, err);
    }
    return [];
  },

  // ----------------------------------------
  // Alerts and satellite image
  // ----------------------------------------

  /** Stations whose latest forecast needs attention (watch, warning, critical). */
  async getAlerts(): Promise<AlertFeedItem[] | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/dashboard/alerts`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) return await res.json();
    } catch (err) {
      console.info('[solarApi.getAlerts] failed:', err);
    }
    return null;
  },

  /**
   * Newest real satellite crop around a station, as an object URL (the caller revokes it).
   * Returns null when the backend has no image yet.
   */
  async getSatelliteCrop(stationId: string): Promise<{ url: string; lastModified: string | null } | null> {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/ingestion/satellite/${stationId}/latest.png`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        const blob = await res.blob();
        return { url: URL.createObjectURL(blob), lastModified: res.headers.get('Last-Modified') };
      }
    } catch (err) {
      console.info('[solarApi.getSatelliteCrop] failed:', err);
    }
    return null;
  },
};
