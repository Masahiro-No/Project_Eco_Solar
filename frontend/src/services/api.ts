/**
 * SolarDSS API Client Service
 * Connects frontend with FastAPI Backend & AI Model Inference Engine.
 * Strictly aligned with Backend Pydantic Schemas in api/stations/schema.py
 * Falls back seamlessly to mock data when backend is not running.
 */

import { API_BASE_URL } from '@/lib/config';

export function getAuthHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('solar_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
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

export interface PredictionResultData {
  job_id: string;
  station_id: string;
  station_name: string;
  predicted_at: string;
  forecast_horizon_hours: number;
  ghi_forecast_curve: number[];
  estimated_power_kw: number;
  target_power_kw: number;
  delta_p_kw: number;
  cloud_trend: string;
  confidence: number;
  alert_level: string;
  recommendation_text: string;
  satellite_image_url?: string;
  /** Timestamp of the newest weather observation the model was fed with */
  data_time?: string | null;
}

export interface SatelliteFrameItem {
  frame_no: number;
  timestamp: string;
  image_url: string;
  time_label?: string;
  source?: string;
}

export interface SatelliteFramesResponse {
  status: string;
  source: string;
  station_id?: string;
  total_frames: number;
  latest_frame: SatelliteFrameItem;
  frames: SatelliteFrameItem[];
}

export interface InferenceEnqueueResponse {
  job_id: string;
  status: string;
  station_id: string;
  target_power_kw: number;
  model_version: string;
  enqueued_at: string;
}

// ==========================================
// Dashboard API Schemas (api/dashboard/schema.py)
// ==========================================

export interface AlertBreakdown {
  green: number;
  yellow: number;
  red: number;
}

export interface DashboardSummaryResponse {
  total_power_kw: number;
  total_target_kw: number;
  total_delta_p_kw: number;
  active_stations_count: number;
  alert_summary: AlertBreakdown;
  last_updated: string;
}

export interface StationDashboardResponse {
  station_id: string;
  station_name: string;
  latitude: number;
  longitude: number;
  target_capacity_kw: number;
  current_ghi_w_m2: number;
  forecast_curve_3h: number[];
  cloud_trend: string;
  confidence: number;
  estimated_power_kw: number;
  delta_p_kw: number;
  alert_level: string;
  recommendation_text: string;
  satellite_image_url?: string;
  last_updated: string;
}

// ==========================================
// API Client Service
// ==========================================

export const solarApi = {
  /**
   * Check if backend API server is online and responding
   */
  async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE_URL}/health`, { method: 'GET', cache: 'no-store' });
      return res.ok;
    } catch {
      return false;
    }
  },

  // ----------------------------------------
  // Stations API (api/stations/router.py)
  // ----------------------------------------

  /**
   * GET /api/stations - Fetch solar stations from Backend DB
   */
  async getStations(limit: number = 100, offset: number = 0, includeArchived: boolean = false): Promise<StationResponse[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/stations?limit=${limit}&offset=${offset}&include_archived=${includeArchived}`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/archived`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/${stationId}`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/${stationId}`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/${stationId}`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/${stationId}`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/${stationId}/restore`, {
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
      const res = await fetch(`${API_BASE_URL}/api/stations/nearest?lat=${lat}&lon=${lon}`, {
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
  // Dashboard API (api/dashboard/router.py)
  // ----------------------------------------

  /**
   * GET /api/dashboard/summary - Aggregate system status from Backend DB
   */
  async getDashboardSummary(): Promise<DashboardSummaryResponse | null> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/dashboard/summary`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error('[solarApi.getDashboardSummary] Error:', err);
    }
    return null;
  },

  /**
   * GET /api/dashboard/station/{id} - Specific station live dashboard from Backend DB
   */
  async getStationDashboard(stationId: string): Promise<StationDashboardResponse | null> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/dashboard/station/${stationId}`, {
        method: 'GET',
        headers: getAuthHeaders(),
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.error(`[solarApi.getStationDashboard] Error for ${stationId}:`, err);
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
      const res = await fetch(`${API_BASE_URL}/api/inference/latest/${stationId}`, {
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
   * Enqueue a new 3-hour solar forecast calculation using the ONNX model
   */
  async triggerPrediction(
    stationId: string = 'ST-001',
    targetKw: number = 5000,
    modelVersion: string = 'v1.0.0'
  ): Promise<InferenceEnqueueResponse | null> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/inference/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          station_id: stationId,
          target_power_kw: targetKw,
          model_version: modelVersion,
        }),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info(`[solarApi.triggerPrediction] Could not enqueue prediction for ${stationId}:`, err);
    }
    return null;
  },

  /**
   * Get forecast results by Job ID
   */
  async getResultByJobId(jobId: string): Promise<{ status: string; result?: PredictionResultData } | null> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/inference/result/${jobId}`, {
        method: 'GET',
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info(`[solarApi.getResultByJobId] Could not fetch result for ${jobId}:`, err);
    }
    return null;
  },

  /**
   * Fetch historical prediction results for chart comparison
   */
  async getPredictionHistory(stationId: string = 'ST-001', limit: number = 20): Promise<PredictionResultData[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/inference/history/${stationId}?limit=${limit}`, {
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
  // Satellite Ingestion API
  // ----------------------------------------

  /**
   * Fetch real-time Himawari-8/9 satellite frames sequence (10-minute cadence)
   */
  async getSatelliteFrames(
    stationId: string = 'ST-001',
    count: number = 12
  ): Promise<SatelliteFrameItem[]> {
    // 1. Try Next.js internal server route (seamlessly queries NICT / backend)
    try {
      const res = await fetch(`/api/satellite/frames?station_id=${stationId}&count=${count}`, {
        method: 'GET',
        cache: 'no-store',
      });
      if (res.ok) {
        const data: SatelliteFramesResponse = await res.json();
        if (data.frames && data.frames.length > 0) {
          return data.frames;
        }
      }
    } catch (err) {
      console.info('[solarApi.getSatelliteFrames] Route handler fetch failed, using direct client fallback:', err);
    }

    // 2. Direct client fallback if API route is unreachable
    try {
      const now = new Date();
      const approx = new Date(now.getTime() - 20 * 60 * 1000);
      const minuteFloor = Math.floor(approx.getUTCMinutes() / 10) * 10;
      const latestDt = new Date(Date.UTC(
        approx.getUTCFullYear(),
        approx.getUTCMonth(),
        approx.getUTCDate(),
        approx.getUTCHours(),
        minuteFloor,
        0
      ));

      const frames: SatelliteFrameItem[] = [];
      for (let i = count - 1; i >= 0; i--) {
        const frameDate = new Date(latestDt.getTime() - i * 10 * 60 * 1000);
        const yyyy = frameDate.getUTCFullYear();
        const mm = String(frameDate.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(frameDate.getUTCDate()).padStart(2, '0');
        const hh = String(frameDate.getUTCHours()).padStart(2, '0');
        const min = String(frameDate.getUTCMinutes()).padStart(2, '0');
        const ss = String(frameDate.getUTCSeconds()).padStart(2, '0');

        const thaiDate = new Date(frameDate.getTime() + 7 * 60 * 60 * 1000);
        const thaiHours = String(thaiDate.getUTCHours()).padStart(2, '0');
        const thaiMinutes = String(thaiDate.getUTCMinutes()).padStart(2, '0');

        frames.push({
          frame_no: count - i,
          timestamp: frameDate.toISOString(),
          image_url: `https://himawari8-dl.nict.go.jp/himawari8/img/D531106/1d/550/${yyyy}/${mm}/${dd}/${hh}${min}${ss}_0_0.png`,
          time_label: `${thaiHours}:${thaiMinutes} น.`,
          source: 'nict_direct',
        });
      }
      return frames;
    } catch {
      return [];
    }
  },

  // ----------------------------------------
  // ConvLSTM Cloud Movement API
  // ----------------------------------------

  /**
   * Fetch ConvLSTM cloud movement prediction & 4-class probabilities
   */
  async getCloudPrediction(stationId: string = 'ST-001'): Promise<CloudPredictionResponse | null> {
    try {
      const res = await fetch(`/api/cloud/prediction?station_id=${stationId}`, {
        method: 'GET',
        cache: 'no-store',
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info('[solarApi.getCloudPrediction] Fetch failed:', err);
    }
    return null;
  },
};

export interface CloudPredictionResponse {
  status: string;
  station_id: string;
  cloud_trend: string;
  confidence: number;
  top_class: {
    id: 'clear' | 'inward' | 'outward' | 'overcast';
    name: string;
    th: string;
    pct: number;
    tone: 'ok' | 'brand' | 'warn' | 'muted';
  };
  classes: {
    id: 'clear' | 'inward' | 'outward' | 'overcast';
    name: string;
    th: string;
    pct: number;
    tone: 'ok' | 'brand' | 'warn' | 'muted';
  }[];
  description: string;
  bess_advisory: string;
  source: string;
  updated_at: string;
}

