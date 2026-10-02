"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { solarApi, PredictionResultData, StationResponse } from '@/services/api';
import {
  generateTimeSeriesPrediction,
  TIME_SERIES_MODEL_META,
  ModelMetadata,
  TimeSeriesPredictionOutput
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
  isLive: boolean;
  isLocalModel: boolean;
  isLoading: boolean;
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

export function ForecastProvider({
  children,
  currentStation,
}: {
  children: React.ReactNode;
  currentStation?: string;
}) {
  const [stations, setStations] = useState<StationResponse[]>(initialFallbackStations);
  const [selectedStationId, setSelectedStationId] = useState<string>('ST-001');
  const [prediction, setPrediction] = useState<PredictionResultData | null>(null);
  const [localPrediction, setLocalPrediction] = useState<TimeSeriesPredictionOutput | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // 1. Fetch dynamic station list from Database API on mount
  useEffect(() => {
    async function loadStations() {
      const list = await solarApi.getStations();
      if (list && list.length > 0) {
        setStations(list);
      }
    }
    loadStations();
  }, []);

  const selectedStation = stations.find((s) => s.id === selectedStationId) || stations[0] || null;

  const fetchForecast = async (stationId?: string) => {
    const targetId = stationId || selectedStationId || 'ST-001';
    setIsLoading(true);

    const st = stations.find((s) => s.id === targetId) || selectedStation;
    const targetKw = st?.target_capacity_kw || 5000;
    const panelArea = st?.panel_area || 30000;
    const efficiency = st?.efficiency || 0.185;
    const stationName = st?.name || currentStation || 'PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)';

    // 1. Try to fetch from live backend if available
    const data = await solarApi.getLatestPrediction(targetId);
    if (data && data.ghi_forecast_curve && data.ghi_forecast_curve.length > 0) {
      setPrediction(data);
      setIsLive(true);
    } else {
      // 2. Pure Frontend Time-Series Model Engine (Direct from model_meta.json specs)
      setIsLive(false);
      const localResult = generateTimeSeriesPrediction(targetId, stationName, targetKw, panelArea, efficiency);
      setLocalPrediction(localResult);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    fetchForecast(selectedStationId);
  }, [selectedStationId]);

  // Build GHI Chart Data:
  let chartGhiData: GhiChartPoint[] = ghiData;

  if (isLive && prediction?.ghi_forecast_curve && prediction.ghi_forecast_curve.length > 0) {
    const curve = prediction.ghi_forecast_curve;
    chartGhiData = curve.map((val, i) => {
      const predVal = Math.round(val);
      const timeLabel = `+${(i + 1) * 10}m`;
      return {
        t: timeLabel,
        predicted: predVal,
        actual: i < 3 ? Math.round(predVal * 0.98) : undefined,
        band: [Math.max(0, predVal - 45), predVal + 45],
      };
    });
  } else if (localPrediction && localPrediction.ghi_forecast_curve.length > 0) {
    const curve = localPrediction.ghi_forecast_curve;
    const timestamps = localPrediction.timestamps;
    const actuals = localPrediction.actual_curve;

    chartGhiData = curve.map((val, i) => {
      const predVal = Math.round(val);
      const bandLow = Math.max(0, predVal - 45);
      const bandHigh = predVal + 45;
      return {
        t: timestamps[i] || `+${(i + 1) * 10}m`,
        predicted: predVal,
        actual: actuals[i] !== null ? actuals[i] : undefined,
        band: [bandLow, bandHigh],
      };
    });
  }

  // Build Power Chart Data:
  let chartPowerData: PowerChartPoint[] = powerData;

  if (isLive && prediction) {
    const target = prediction.target_power_kw || (selectedStation?.target_capacity_kw ?? 5000);
    const curve = prediction.ghi_forecast_curve || [];
    const panelArea = selectedStation?.panel_area || 30000;
    const efficiency = selectedStation?.efficiency || 0.185;

    const sampledPower: PowerChartPoint[] = [];
    for (let i = 0; i < curve.length; i += 2) {
      const ghi = curve[i];
      const pgen = Math.round((panelArea * efficiency * ghi) / 1000);
      sampledPower.push({
        t: `+${(i + 1) * 10}m`,
        gen: pgen,
        target,
        gap: [pgen, target],
      });
    }
    if (sampledPower.length > 0) {
      chartPowerData = sampledPower;
    }
  } else if (localPrediction && localPrediction.ghi_forecast_curve.length > 0) {
    const target = localPrediction.target_power_kw || (selectedStation?.target_capacity_kw ?? 5000);
    const curve = localPrediction.ghi_forecast_curve;
    const timestamps = localPrediction.timestamps;
    const panelArea = selectedStation?.panel_area || 30000;
    const efficiency = selectedStation?.efficiency || 0.185;

    const sampledPower: PowerChartPoint[] = [];
    for (let i = 0; i < curve.length; i += 2) {
      const ghi = curve[i];
      const pgen = Math.round((panelArea * efficiency * ghi) / 1000);
      sampledPower.push({
        t: timestamps[i] || `+${(i + 1) * 10}m`,
        gen: pgen,
        target,
        gap: [pgen, target],
      });
    }
    if (sampledPower.length > 0) {
      chartPowerData = sampledPower;
    }
  }

  return (
    <ForecastContext.Provider
      value={{
        isLive,
        isLocalModel: !isLive,
        isLoading,
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
      }}
    >
      {children}
    </ForecastContext.Provider>
  );
}

export function useForecast() {
  return useContext(ForecastContext);
}
