"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { solarApi, PredictionResultData, StationResponse } from '@/services/api';
import { forecastTimeLabel } from '@/lib/time';

export type GhiChartPoint = {
  t: string;
  /** Final forecast: LSTM blended with the satellite cloud forecast */
  blend: number;
  /** LSTM forecast before blending */
  lstm: number | null;
  /** Weight of the satellite branch at this step, in % */
  weightPct: number | null;
  /** Forecast cloud cover in the area around the station, in % */
  cloudPct: number | null;
  /** Expected loss of GHI against clear sky from the satellite branch, in % */
  lossPct: number | null;
};

export type PowerChartPoint = {
  t: string;
  gen: number;
  /** Target at this time: follows the sun, never above P_target */
  target: number;
};

export type ForecastContextType = {
  /** true = a real model forecast of the selected station is on screen */
  isLive: boolean;
  isLoading: boolean;
  error: string | null;
  /** When the latest prediction was produced (null if there is none) */
  lastUpdated: string | null;
  stations: StationResponse[];
  stationsLoaded: boolean;
  selectedStationId: string;
  selectedStation: StationResponse | null;
  setSelectedStationId: (id: string) => void;
  prediction: PredictionResultData | null;
  refreshForecast: (stationId?: string, opts?: { silent?: boolean }) => Promise<void>;
  reloadStations: () => Promise<void>;
  chartGhiData: GhiChartPoint[];
  chartPowerData: PowerChartPoint[];
};

const ForecastContext = createContext<ForecastContextType>({
  isLive: false,
  isLoading: false,
  error: null,
  lastUpdated: null,
  stations: [],
  stationsLoaded: false,
  selectedStationId: '',
  selectedStation: null,
  setSelectedStationId: () => {},
  prediction: null,
  refreshForecast: async () => {},
  reloadStations: async () => {},
  chartGhiData: [],
  chartPowerData: [],
});

/** How often the dashboard re-reads the latest prediction (the backend produces one every 10 min). */
const POLL_INTERVAL_MS = 60_000;

export function ForecastProvider({ children }: { children: React.ReactNode }) {
  const [stations, setStations] = useState<StationResponse[]>([]);
  const [stationsLoaded, setStationsLoaded] = useState(false);
  const [selectedStationId, setSelectedStationId] = useState<string>('');
  const [prediction, setPrediction] = useState<PredictionResultData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against out-of-order responses when the station changes quickly
  const requestSeq = useRef(0);
  const predictionRef = useRef<PredictionResultData | null>(null);
  predictionRef.current = prediction;

  const reloadStations = useCallback(async () => {
    const list = await solarApi.getStations();
    setStations(list ?? []);
    setStationsLoaded(true);
    if (list && list.length > 0) {
      setSelectedStationId((cur) => (cur && list.some((s) => s.id === cur) ? cur : list[0].id));
    }
  }, []);

  useEffect(() => {
    reloadStations();
  }, [reloadStations]);

  const selectedStation = useMemo(
    () => stations.find((s) => s.id === selectedStationId) || null,
    [stations, selectedStationId]
  );

  const fetchForecast = useCallback(
    async (stationId?: string, opts?: { silent?: boolean }) => {
      const silent = !!opts?.silent;
      const targetId = stationId || selectedStationId;
      if (!targetId) return;
      const seq = ++requestSeq.current;
      if (!silent) setIsLoading(true);
      setError(null);

      try {
        const data = await solarApi.getLatestPrediction(targetId);
        if (seq !== requestSeq.current) return; // a newer request superseded this one

        if (data && data.ghi_forecast_curve && data.ghi_forecast_curve.length > 0) {
          setPrediction(data);
        } else if (!(silent && predictionRef.current?.station_id === targetId)) {
          // No real forecast for this station: show nothing rather than a substitute.
          // (A failed background refresh keeps the last real result; its age is shown to the user.)
          setPrediction(null);
        }
      } catch (err) {
        if (seq !== requestSeq.current) return;
        console.error('[ForecastProvider] forecast failed', err);
        setError('Unable to load forecast');
        if (!(silent && predictionRef.current?.station_id === targetId)) setPrediction(null);
      } finally {
        if (seq === requestSeq.current && !silent) setIsLoading(false);
      }
    },
    [selectedStationId]
  );

  useEffect(() => {
    setPrediction(null);
    fetchForecast(selectedStationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStationId]);

  // Auto-refresh: pick up each new 10-minute prediction without a page reload
  const fetchRef = useRef(fetchForecast);
  fetchRef.current = fetchForecast;
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') {
        fetchRef.current(selectedStationId, { silent: true });
      }
    };
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [selectedStationId]);

  const isLive = !!prediction;

  const chartGhiData = useMemo<GhiChartPoint[]>(() => {
    if (!prediction) return [];
    const base = prediction.data_time || prediction.predicted_at;
    return prediction.ghi_forecast_curve.map((v, i) => {
      const lstm = prediction.ghi_forecast_lstm_raw?.[i];
      const w = prediction.blend_weight?.[i];
      const c = prediction.cloud_coverage_pct?.[i];
      const loss = prediction.sat_ghi_loss_pct?.[i];
      return {
        t: forecastTimeLabel(base, i + 1),
        blend: Math.round(v),
        lstm: lstm === undefined || lstm === null ? null : Math.round(lstm),
        weightPct: w === undefined || w === null ? null : Math.round(w * 100),
        cloudPct: c === undefined || c === null ? null : Math.round(c),
        lossPct: loss === undefined || loss === null ? null : Math.round(loss),
      };
    });
  }, [prediction]);

  const chartPowerData = useMemo<PowerChartPoint[]>(() => {
    if (!prediction || !selectedStation) return [];
    const base = prediction.data_time || prediction.predicted_at;
    // Same formula as the backend decision rules: P_gen = A * eta * GHI / 1000, on the blended GHI
    return prediction.ghi_forecast_curve.map((ghi, i) => ({
      t: forecastTimeLabel(base, i + 1),
      gen: Math.round((selectedStation.panel_area * selectedStation.efficiency * ghi) / 1000),
      target: Math.round(prediction.target_profile_kw?.[i] ?? prediction.target_power_kw),
    }));
  }, [prediction, selectedStation]);

  const value = useMemo<ForecastContextType>(
    () => ({
      isLive,
      isLoading,
      error,
      lastUpdated: prediction ? prediction.predicted_at : null,
      stations,
      stationsLoaded,
      selectedStationId,
      selectedStation,
      setSelectedStationId,
      prediction,
      refreshForecast: fetchForecast,
      reloadStations,
      chartGhiData,
      chartPowerData,
    }),
    [
      isLive, isLoading, error, stations, stationsLoaded, selectedStationId, selectedStation,
      prediction, fetchForecast, reloadStations, chartGhiData, chartPowerData,
    ]
  );

  return <ForecastContext.Provider value={value}>{children}</ForecastContext.Provider>;
}

export function useForecast() {
  return useContext(ForecastContext);
}
