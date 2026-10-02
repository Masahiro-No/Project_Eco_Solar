"use client";

import React, { useState, useEffect } from 'react';
import {
  CloudIcon,
  Maximize2Icon,
  XIcon,
  RefreshCwIcon,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { cloudClasses } from '@/data/dashboard';
import { solarApi, SatelliteFrameItem, CloudPredictionResponse } from '@/services/api';
import { useForecast } from '@/context/ForecastContext';

const toneStyles = {
  ok: { box: 'border-ok/40 bg-ok-soft', text: 'text-ok' },
  brand: { box: 'border-brand-mid bg-brand-soft ring-1 ring-brand-mid', text: 'text-brand' },
  warn: { box: 'border-warn/40 bg-warn-soft', text: 'text-warn' },
  muted: { box: 'border-slate-200 bg-slate-50', text: 'text-slate-600' },
};

type CloudKey = 'cloud_clear' | 'cloud_inward' | 'cloud_outward' | 'cloud_overcast';

const cloudDescMap: Record<string, CloudKey> = {
  clear: 'cloud_clear',
  inward: 'cloud_inward',
  outward: 'cloud_outward',
  overcast: 'cloud_overcast',
};

// Map backend CloudTrend enum to cloudClasses id
const backendTrendMap: Record<string, string> = {
  Clear: 'clear',
  Inward: 'inward',
  Outward: 'outward',
  Overcast: 'overcast',
};

const FALLBACK_IMAGE = '/2de8a7c6-3c78-4961-9471-af149bf0e789.jpg';

export function CloudMovement() {
  const t = useTranslations('common');
  const { prediction } = useForecast();

  // Satellite latest frame state
  const [latestFrame, setLatestFrame] = useState<SatelliteFrameItem | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isZoomed, setIsZoomed] = useState<boolean>(false);
  const [modalMode, setModalMode] = useState<'focused' | 'full'>('focused');
  const [imgError, setImgError] = useState<boolean>(false);

  // ConvLSTM Cloud Prediction API state
  const [cloudData, setCloudData] = useState<CloudPredictionResponse | null>(null);

  // Fetch only the latest satellite frame & ConvLSTM cloud movement prediction from API
  const fetchData = async () => {
    try {
      setIsRefreshing(true);
      const [framesRes, cloudRes] = await Promise.all([
        solarApi.getSatelliteFrames('ST-001', 1), // Fetch only the single latest frame
        solarApi.getCloudPrediction('ST-001'),
      ]);

      if (framesRes && framesRes.length > 0) {
        setLatestFrame(framesRes[0]);
        setImgError(false);
      }

      if (cloudRes && cloudRes.classes && cloudRes.classes.length > 0) {
        setCloudData(cloudRes);
      }
    } catch (err) {
      console.warn('[CloudMovement] Could not fetch live data:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh real satellite feed & cloud prediction every 5 minutes
    const interval = setInterval(fetchData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // Synchronize Cloud Prediction with API response or model prediction
  const currentClasses = cloudData?.classes || (prediction?.cloud_trend ? cloudClasses.map((c) => {
    const activeTrendKey = backendTrendMap[prediction.cloud_trend] || 'inward';
    if (c.id === activeTrendKey) {
      const confidencePct = prediction.confidence ? Math.round(prediction.confidence * 100) : 85;
      return { ...c, pct: confidencePct };
    }
    return c;
  }) : cloudClasses);

  const top = cloudData?.top_class || currentClasses.reduce((a, b) => (b.pct > a.pct ? b : a));

  const currentImageUrl = latestFrame?.image_url || FALLBACK_IMAGE;

  // Format time label for bottom caption (e.g., "ล่าสุด 22:00 น. (ภาพถ่ายดาวเทียมสด)")
  const rawTime = latestFrame?.time_label ? latestFrame.time_label.split('(')[0].trim() : null;

  return (
    <>
      <Panel
        title={t('cloud_prediction_title')}
        icon={<CloudIcon className="h-5 w-5 text-slate-700" />}
        className="h-full"
        action={
          <button
            onClick={fetchData}
            title="Refresh satellite & AI prediction"
            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
            disabled={isRefreshing}
          >
            <RefreshCwIcon className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        }
      >
        <div className="grid min-h-0 flex-1 grid-cols-[1.25fr_1.1fr] gap-3.5">
          {/* Left Column: AI Cloud Classification (Fetched from ConvLSTM API) */}
          <div className="flex flex-col">
            <div className="flex items-stretch gap-3">
              <div className="flex flex-1 items-center overflow-hidden rounded-lg bg-brand-soft">
                <span className="flex h-full w-14 items-center justify-center bg-[#d7e5fb]">
                  <CloudIcon className="h-8 w-8 text-[#1e3a8a]" strokeWidth={1.8} />
                </span>
                <div className="px-3 py-2 min-w-0">
                  <p className="text-[20px] font-bold leading-tight text-[#1e3a8a] truncate">{top.name}</p>
                  <p className="text-[12.5px] font-semibold text-[#1e3a8a] truncate">
                    {top.th ? `${top.name} (${top.th})` : t(cloudDescMap[top.id])}
                  </p>
                </div>
              </div>
              <div className="flex w-[96px] flex-col justify-center">
                <p className="text-[11.5px] font-medium text-slate-600">{t('cloud_confidence')}</p>
                <p className="text-[22px] font-bold leading-tight text-ink">{top.pct}%</p>
                <div
                  className="mt-1 h-2 rounded-full bg-slate-100"
                  role="progressbar"
                  aria-valuenow={top.pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div className="h-2 rounded-full bg-ok transition-all duration-500" style={{ width: `${top.pct}%` }} />
                </div>
              </div>
            </div>

            <p className="mb-1.5 mt-auto pt-2 text-[12.5px] font-semibold text-ink">
              {t('cloud_4_classes')}
            </p>
            <div className="grid grid-cols-4 gap-1.5">
              {currentClasses.map((c) => {
                const s = toneStyles[c.tone];
                const isSelected = c.id === top.id;
                return (
                  <div
                    key={c.id}
                    className={`rounded-lg border px-1.5 py-1.5 text-center transition-all ${
                      isSelected ? 'ring-2 ring-brand border-brand bg-brand-soft/40 shadow-xs' : s.box
                    }`}
                  >
                    <p className={`text-[11.5px] font-bold truncate ${c.tone === 'muted' ? 'text-ink' : s.text}`}>
                      {c.name}
                    </p>
                    <p className={`truncate text-[10px] font-medium ${s.text}`}>
                      {c.th ? `${c.name} (${c.th.slice(0, 8)}...)` : t(cloudDescMap[c.id])}
                    </p>
                    <p className={`mt-0.5 text-[12px] font-bold ${s.text}`}>{c.pct}%</p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Clean Regional Satellite View (Southern Thailand Focus) */}
          <figure className="flex min-h-0 flex-col">
            <figcaption className="mb-1.5 text-[12px] font-semibold text-ink">
              {t('satellite_himawari')}
            </figcaption>

            <div
              className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-line bg-slate-900 flex items-center justify-center group cursor-pointer"
              onClick={() => setIsZoomed(true)}
              title="คลิกเพื่อขยายภาพ"
            >
              {isLoading ? (
                <div className="flex flex-col items-center justify-center gap-1.5 text-slate-400 py-6">
                  <RefreshCwIcon className="h-5 w-5 animate-spin text-brand-mid" />
                  <span className="text-[11px]">กำลังโหลดภาพถ่ายดาวเทียม...</span>
                </div>
              ) : (
                <img
                  src={imgError ? FALLBACK_IMAGE : currentImageUrl}
                  alt="Himawari Satellite - Southern Thailand"
                  onError={() => setImgError(true)}
                  style={
                    !imgError && currentImageUrl !== FALLBACK_IMAGE
                      ? {
                          transformOrigin: '18% 43%', // Precision focal point for Southern Thailand & Gulf of Thailand
                          transform: 'scale(3.1)',     // Crop out outer space and zoom specifically into Southern Thailand
                        }
                      : undefined
                  }
                  className="h-full w-full object-cover transition-transform duration-300"
                />
              )}

              {/* Hover Zoom Hint */}
              <div className="absolute top-2 right-2 rounded-md bg-black/60 p-1 text-white/80 opacity-0 group-hover:opacity-100 transition-opacity">
                <Maximize2Icon className="h-3.5 w-3.5" />
              </div>
            </div>

            <p className="mt-1.5 text-[11px] font-medium text-muted">
              {rawTime ? `ล่าสุด ${rawTime} (ภาพถ่ายดาวเทียมสด)` : t('latest_frame')}
            </p>
          </figure>
        </div>
      </Panel>

      {/* Fullscreen Zoom Lightbox Modal */}
      {isZoomed && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4">
          <div className="relative max-w-4xl w-full bg-slate-950 rounded-xl overflow-hidden border border-slate-800 shadow-2xl flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900 text-white">
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm">Himawari-8/9 Real-time Satellite Observation</span>
                <span className="text-xs text-slate-400 tabular-nums">
                  ({rawTime ? `เวลา ${rawTime}` : 'ภาพสด'})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex rounded-lg bg-slate-800 p-0.5 text-xs">
                  <button
                    onClick={() => setModalMode('focused')}
                    className={`px-2.5 py-1 rounded font-medium transition-colors ${
                      modalMode === 'focused' ? 'bg-brand text-white shadow-xs' : 'text-slate-300 hover:text-white'
                    }`}
                  >
                    โฟกัสภาคใต้
                  </button>
                  <button
                    onClick={() => setModalMode('full')}
                    className={`px-2.5 py-1 rounded font-medium transition-colors ${
                      modalMode === 'full' ? 'bg-brand text-white shadow-xs' : 'text-slate-300 hover:text-white'
                    }`}
                  >
                    ภาพเต็มแผ่นดิสก์
                  </button>
                </div>
                <button
                  onClick={() => setIsZoomed(false)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
                >
                  <XIcon className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 min-h-0 p-4 flex items-center justify-center bg-black overflow-hidden">
              <div className="relative max-h-[70vh] aspect-video w-full overflow-hidden rounded-lg flex items-center justify-center bg-slate-900">
                <img
                  src={imgError ? FALLBACK_IMAGE : currentImageUrl}
                  alt="Himawari satellite high resolution"
                  style={
                    modalMode === 'focused' && !imgError && currentImageUrl !== FALLBACK_IMAGE
                      ? {
                          transformOrigin: '18% 43%',
                          transform: 'scale(2.8)',
                        }
                      : undefined
                  }
                  className="h-full w-full object-contain transition-transform duration-300"
                />
              </div>
            </div>

            <div className="px-4 py-2.5 border-t border-slate-800 bg-slate-900/90 text-xs text-slate-400 flex items-center justify-between">
              <span>แหล่งข้อมูล: NICT Japan & Japan Meteorological Agency (JMA) — พิกัดภาคใต้ (Lat 6°N - 10°N, Lon 98°E - 102°E)</span>
              <span className="text-emerald-400 font-medium">Real-time Ingest Active</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}