"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { solarApi, PredictionResultData, StationResponse } from '@/services/api';
import {
  generateTimeSeriesPrediction,
  TIME_SERIES_MODEL_META,
  ModelMetadata,
  TimeSeriesPredictionOutput,
} from '@/services/timeSeriesModel';
import { ghiData, powerData, stations as fallbackStations } from '@/data/dashboard';

export type GhiChartPoint = {
  t: string;
  actual?: number | null;
  predicted: number;
  band: [number, number] | number[];
};

export type PowerChartPoint = {
  t: string;
  gen: number;
  target: number;
  gap: [number, number];
};

export type ForecastContextType = {
  /** true = data comes from the backend inference service */
  isLive: boolean;
  /** true = data comes from the in-browser simulation / static mock data */
  isLocalModel: boolean;
  isLoading: boolean;
  error: string | null;
  stations: StationResponse[];
  selectedStationId: string;
  selectedStation: StationResponse | null;
  setSelectedStationId: (id: string) => void;
  prediction: PredictionResultData | null;
  localPrediction: TimeSeriesPredictionOutput | null;
  modelMeta: ModelMetadata;
  refreshForecast: (stationId?: string) => Promise<void>;
  chartGhiData: GhiChartPoint[];
  chartPowerData: PowerChartPoint[];
};

const initialFallbackStations: StationResponse[] = fallbackStations.map((s) => ({
  id: s.id,
  name: s.name,
  latitude: s.latitude,
  longitude: s.longitude,
  panel_area: s.panel_area,
  efficiency: s.efficiency,
  target_capacity_kw: s.target_capacity_kw,
  is_active: s.is_active,
}));

const ForecastContext = createContext<ForecastContextType>({
  isLive: false,
  isLocalModel: true,
  isLoading: false,
  error: null,
  stations: initialFallbackStations,
  selectedStationId: 'ST-001',
  selectedStation: initialFallbackStations[0],
  setSelectedStationId: () => {},
  prediction: null,
  localPrediction: null,
  modelMeta: TIME_SERIES_MODEL_META,
  refreshForecast: async () => {},
  chartGhiData: ghiData,
  chartPowerData: powerData,
});

const BAND = 45;

/** Shared builders so live and local predictions go through the same code path. */
function buildGhiChart(
  curve: number[],
  labelAt: (i: number) => string,
  actualAt: (i: number, predicted: number) => number | null | undefined
): GhiChartPoint[] {
  return curve.map((val, i) => {
    const predicted = Math.round(val);
    return {
      t: labelAt(i),
      predicted,
      actual: actualAt(i, predicted),
      band: [Math.max(0, predicted - BAND), predicted + BAND],
    };
  });
}

function buildPowerChart(
  curve: number[],
  labelAt: (i: number) => string,
  target: number,
  panelArea: number,
  efficiency: number
): PowerChartPoint[] {
  const points: PowerChartPoint[] = [];
  for (let i = 0; i < curve.length; i += 2) {
    const gen = Math.round((panelArea * efficiency * curve[i]) / 1000);
    points.push({ t: labelAt(i), gen, target, gap: [gen, target] });
  }
  return points;
}

const offsetLabel = (i: number) => `+${(i + 1) * 10}m`;

export function ForecastProvider({ children }: { children: React.ReactNode }) {
  const [stations, setStations] = useState<StationResponse[]>(initialFallbackStations);
  const [selectedStationId, setSelectedStationId] = useState<string>('ST-001');
  const [prediction, setPrediction] = useState<PredictionResultData | null>(null);
  const [localPrediction, setLocalPrediction] = useState<TimeSeriesPredictionOutput | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guards against out-of-order responses when the station changes quickly
  const requestSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    solarApi.getStations().then((list) => {
      if (!cancelled && list && list.length > 0) setStations(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedStation = useMemo(
    () => stations.find((s) => s.id === selectedStationId) || stations[0] || null,
    [stations, selectedStationId]
  );

  const fetchForecast = useCallback(
    async (stationId?: string) => {
      const targetId = stationId || selectedStationId || 'ST-001';
      const seq = ++requestSeq.current;
      setIsLoading(true);
      setError(null);

      const st = stations.find((s) => s.id === targetId) || selectedStation;
      const targetKw = st?.target_capacity_kw || 5000;
      const panelArea = st?.panel_area || 30000;
      const efficiency = st?.efficiency || 0.185;
      const stationName = st?.name || 'PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)';

      try {
        const data = await solarApi.getLatestPrediction(targetId);
        if (seq !== requestSeq.current) return; // a newer request superseded this one

        if (data && data.ghi_forecast_curve && data.ghi_forecast_curve.length > 0) {
          setPrediction(data);
          setLocalPrediction(null);
          setIsLive(true);
        } else {
          setPrediction(null);
          setIsLive(false);
          setLocalPrediction(generateTimeSeriesPrediction(targetId, stationName, targetKw, panelArea, efficiency));
        }
      } catch (err) {
        if (seq !== requestSeq.current) return;
        console.error('[ForecastProvider] forecast failed', err);
        setError('Unable to load forecast');
        setPrediction(null);
        setIsLive(false);
        setLocalPrediction(generateTimeSeriesPrediction(targetId, stationName, targetKw, panelArea, efficiency));
      } finally {
        if (seq === requestSeq.current) setIsLoading(false);
      }
    },
    [selectedStationId, stations, selectedStation]
  );

  useEffect(() => {
    fetchForecast(selectedStationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStationId]);

  const chartGhiData = useMemo<GhiChartPoint[]>(() => {
    if (isLive && prediction?.ghi_forecast_curve?.length) {
      return buildGhiChart(prediction.ghi_forecast_curve, offsetLabel, (i, p) =>
        i < 3 ? Math.round(p * 0.98) : undefined
      );
    }
    if (localPrediction && localPrediction.ghi_forecast_curve.length > 0) {
      const { timestamps, actual_curve } = localPrediction;
      return buildGhiChart(
        localPrediction.ghi_forecast_curve,
        (i) => timestamps[i] || offsetLabel(i),
        (i) => (actual_curve[i] !== null ? actual_curve[i] : undefined)
      );
    }
    return ghiData;
  }, [isLive, prediction, localPrediction]);

  const chartPowerData = useMemo<PowerChartPoint[]>(() => {
    const panelArea = selectedStation?.panel_area || 30000;
    const efficiency = selectedStation?.efficiency || 0.185;
    const fallbackTarget = selectedStation?.target_capacity_kw ?? 5000;

    let points: PowerChartPoint[] = [];
    if (isLive && prediction) {
      points = buildPowerChart(
        prediction.ghi_forecast_curve || [],
        offsetLabel,
        prediction.target_power_kw || fallbackTarget,
        panelArea,
        efficiency
      );
    } else if (localPrediction && localPrediction.ghi_forecast_curve.length > 0) {
      const { timestamps } = localPrediction;
      points = buildPowerChart(
        localPrediction.ghi_forecast_curve,
        (i) => timestamps[i] || offsetLabel(i),
        localPrediction.target_power_kw || fallbackTarget,
        panelArea,
        efficiency
      );
    }
    return points.length > 0 ? points : powerData;
  }, [isLive, prediction, localPrediction, selectedStation]);

  const value = useMemo<ForecastContextType>(
    () => ({
      isLive,
      isLocalModel: !isLive,
      isLoading,
      error,
      stations,
      selectedStationId,
      selectedStation,
      setSelectedStationId,
      prediction,
      localPrediction,
      modelMeta: TIME_SERIES_MODEL_META,
      refreshForecast: fetchForecast,
      chartGhiData,
      chartPowerData,
    }),
    [
      isLive, isLoading, error, stations, selectedStationId, selectedStation,
      prediction, localPrediction, fetchForecast, chartGhiData, chartPowerData,
    ]
  );

  return <ForecastContext.Provider value={value}>{children}</ForecastContext.Provider>;
}

export function useForecast() {
  return useContext(ForecastContext);
}
