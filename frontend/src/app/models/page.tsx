"use client";

import React from 'react';
import { BrainIcon, CpuIcon, CheckCircle2Icon, PlayIcon, LayersIcon, HardDriveIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';

const models = [
  {
    name: 'ConvLSTM Satellite Cloud Motion',
    type: 'Spatiotemporal Deep Learning',
    version: 'v2.4.1',
    dataset: 'Himawari-8/9 NetCDF4 Images (2020-2025)',
    accuracy: '94.2%',
    latency: '115 ms',
    parameters: '14.8M Params',
    status: 'Active (Inference Mode)',
    lastTrained: '30 ก.ย. 2026, 02:00 น.'
  },
  {
    name: 'Bi-LSTM GHI Irradiance Forecaster',
    type: 'Recurrent Neural Network (Time Series)',
    version: 'v3.1.0',
    dataset: 'Solar Pyranometer Station Logs (15-min)',
    accuracy: '95.4% R²',
    latency: '35 ms',
    parameters: '4.2M Params',
    status: 'Active (Inference Mode)',
    lastTrained: '29 ก.ย. 2026, 23:45 น.'
  },
  {
    name: 'XGBoost PV Yield Output Estimator',
    type: 'Gradient Boosted Decision Trees',
    version: 'v1.8.2',
    dataset: 'Inverter SCADA & Ambient Temperature',
    accuracy: '96.1% R²',
    latency: '12 ms',
    parameters: '500 Trees',
    status: 'Active (Inference Mode)',
    lastTrained: '28 ก.ย. 2026, 12:00 น.'
  }
];

export default function ModelsPage() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-100 text-purple-600">
            <BrainIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('models_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('models_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Model Cards */}
      <div className="grid grid-cols-3 gap-4">
        {models.map((m) => (
          <article key={m.name} className="flex flex-col rounded-xl border border-line bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50 text-purple-600">
                  <CpuIcon className="h-5 w-5" />
                </span>
                <div>
                  <h3 className="text-[15px] font-bold text-ink leading-snug">{m.name}</h3>
                  <p className="text-[12px] font-medium text-slate-500">{m.type}</p>
                </div>
              </div>
              <span className="rounded-full bg-ok-soft px-2.5 py-0.5 text-[11px] font-bold text-ok">
                {m.version}
              </span>
            </div>

            <div className="my-4 grid grid-cols-2 gap-2.5 rounded-lg bg-canvas p-3 text-[12.5px]">
              <div>
                <p className="text-muted">{t('model_accuracy')}</p>
                <p className="text-[16px] font-bold text-ink">{m.accuracy}</p>
              </div>
              <div>
                <p className="text-muted">{t('model_latency')}</p>
                <p className="text-[16px] font-bold text-ink">{m.latency}</p>
              </div>
              <div className="col-span-2 pt-1 border-t border-line/60">
                <p className="text-muted text-[11.5px]">{t('model_size')} <span className="font-semibold text-slate-700">{m.parameters}</span></p>
                <p className="text-muted text-[11.5px]">{t('model_dataset')} <span className="font-medium text-slate-700">{m.dataset}</span></p>
              </div>
            </div>

            <div className="mt-auto flex items-center justify-between pt-2 border-t border-line text-[12px]">
              <span className="flex items-center gap-1.5 font-medium text-ok">
                <span className="h-2 w-2 rounded-full bg-ok animate-pulse" />
                {t('ready_to_use')}
              </span>
              <button className="flex items-center gap-1 rounded-lg border border-line bg-white px-2.5 py-1 font-semibold text-slate-700 hover:bg-canvas">
                <PlayIcon className="h-3 w-3 fill-slate-700" />
                {t('retrain')}
              </button>
            </div>
          </article>
        ))}
      </div>

      {/* Model Performance & Pipeline Architecture */}
      <Panel title={t('pipeline_arch')} icon={<LayersIcon className="h-5 w-5 text-brand" />}>
        <div className="grid grid-cols-4 gap-3 p-2 text-center">
          <div className="rounded-xl border border-line bg-canvas p-4">
            <span className="inline-block rounded-full bg-blue-100 p-2 text-blue-600 mb-2">
              <HardDriveIcon className="h-6 w-6" />
            </span>
            <h4 className="font-bold text-[14px] text-ink">1. Data Ingestion</h4>
            <p className="text-[12px] text-slate-600 mt-1">รับภาพถ่ายดาวเทียม Himawari ทุก 10 นาที และค่ารังสีภาคพื้นดิน</p>
          </div>
          <div className="rounded-xl border border-line bg-canvas p-4">
            <span className="inline-block rounded-full bg-purple-100 p-2 text-purple-600 mb-2">
              <CpuIcon className="h-6 w-6" />
            </span>
            <h4 className="font-bold text-[14px] text-ink">2. Feature Extraction</h4>
            <p className="text-[12px] text-slate-600 mt-1">ConvLSTM สกัดเวกเตอร์การเคลื่อนตัวและทิศทางของกลุ่มเมฆ</p>
          </div>
          <div className="rounded-xl border border-line bg-canvas p-4">
            <span className="inline-block rounded-full bg-amber-100 p-2 text-amber-600 mb-2">
              <BrainIcon className="h-6 w-6" />
            </span>
            <h4 className="font-bold text-[14px] text-ink">3. Solar Forecast</h4>
            <p className="text-[12px] text-slate-600 mt-1">Bi-LSTM ทำนายค่า GHI และ XGBoost แปลงเป็นกำลังไฟฟ้า (kW)</p>
          </div>
          <div className="rounded-xl border border-line bg-canvas p-4">
            <span className="inline-block rounded-full bg-emerald-100 p-2 text-emerald-600 mb-2">
              <CheckCircle2Icon className="h-6 w-6" />
            </span>
            <h4 className="font-bold text-[14px] text-ink">4. Decision Support</h4>
            <p className="text-[12px] text-slate-600 mt-1">คำนวณกำลังไฟฟ้าสำรอง (ΔP) และแจ้งเตือนผู้ควบคุมโครงข่าย</p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
