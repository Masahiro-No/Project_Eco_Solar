/**
 * SolarDSS API Client Service
 * Connects frontend with FastAPI Backend & AI Model Inference Engine.
 * Falls back seamlessly to mock data when backend is not running.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface StationDto {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  panel_area: number;
  efficiency: number;
  target_capacity_kw: number;
  is_active: boolean;
}

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
}

export interface InferenceEnqueueResponse {
  job_id: string;
  status: string;
  station_id: string;
  target_power_kw: number;
  model_version: string;
  enqueued_at: string;
}

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

  /**
   * Fetch all active solar stations from DB
   */
  async getStations(): Promise<StationDto[]> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/stations`, { method: 'GET', cache: 'no-store' });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.info('[solarApi.getStations] Backend offline, using local fallback', err);
    }
    return [];
  },

  /**
   * Fetch the latest model forecast result for a given station
   */
  async getLatestPrediction(stationId: string = 'ST-001'): Promise<PredictionResultData | null> {
    try {
      const res = await fetch(`${API_BASE_URL}/api/inference/latest/${stationId}`, {
        method: 'GET',
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
    targetKw: number = 850,
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
};
