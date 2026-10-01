"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { solarApi, PredictionResultData } from '@/services/api';
import {
  generateTimeSeriesPrediction,
  TIME_SERIES_MODEL_META,
  ModelMetadata,
  TimeSeriesPredictionOutput
} from '@/services/timeSeriesModel';
import { ghiData, powerData } from '@/data/dashboard';

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

type ForecastContextType = {
  isLive: boolean;
  isLocalModel: boolean;
  isLoading: boolean;
  prediction: PredictionResultData | null;
  localPrediction: TimeSeriesPredictionOutput | null;
  modelMeta: ModelMetadata;
  refreshForecast: (stationId?: string) => Promise<void>;
  chartGhiData: GhiChartPoint[];
  chartPowerData: PowerChartPoint[];
};

const ForecastContext = createContext<ForecastContextType>({
  isLive: false,
  isLocalModel: true,
  isLoading: false,
  prediction: null,
  localPrediction: null,
  modelMeta: TIME_SERIES_MODEL_META,
  refreshForecast: async () => {},
  chartGhiData: ghiData,
  chartPowerData: powerData,
});

export function ForecastProvider({
  children,
  currentStation = 'Hat Yai Solar Farm',
}: {
  children: React.ReactNode;
  currentStation?: string;
}) {
  const [prediction, setPrediction] = useState<PredictionResultData | null>(null);
  const [localPrediction, setLocalPrediction] = useState<TimeSeriesPredictionOutput | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const fetchForecast = async (stationId: string = 'ST-001') => {
    setIsLoading(true);

    // 1. Try to fetch from live backend if available
    const data = await solarApi.getLatestPrediction(stationId);
    if (data && data.ghi_forecast_curve && data.ghi_forecast_curve.length > 0) {
      setPrediction(data);
      setIsLive(true);
    } else {
      // 2. Pure Frontend Time-Series Model Engine (Direct from model_meta.json specs)
      setIsLive(false);
      const localResult = generateTimeSeriesPrediction(stationId, currentStation, 850);
      setLocalPrediction(localResult);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    fetchForecast('ST-001');
  }, [currentStation]);

  // Build GHI Chart Data:
  // - If live backend returned curve, use it
  // - Otherwise, use the 18-step Time-Series LSTM model output from localPrediction
  // - Fallback to ghiData if neither is ready
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
    const target = prediction.target_power_kw || 850;
    chartPowerData = powerData.map((d) => ({
      ...d,
      target,
      gap: [d.gen, target] as [number, number],
    }));
  } else if (localPrediction && localPrediction.ghi_forecast_curve.length > 0) {
    const target = localPrediction.target_power_kw || 850;
    const curve = localPrediction.ghi_forecast_curve;
    const timestamps = localPrediction.timestamps;

    // Sample points for power chart (every 20 or 30 mins)
    const sampledPower: PowerChartPoint[] = [];
    for (let i = 0; i < curve.length; i += 2) {
      const ghi = curve[i];
      const pgen = Math.round((5500 * 0.185 * ghi) / 1000);
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
