"use client";

import React from 'react';
import { ActivityIcon, CheckCircle2Icon, ServerIcon, DatabaseIcon, CpuIcon, HardDriveIcon, RadioIcon, BarChart2Icon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';

const infrastructureServices = [
  { name: 'FastAPI Central API', role: 'Business Logic, Auth & Endpoints', port: '8000', uptime: '99.98%', latency: '24ms', status: 'Healthy', icon: ServerIcon },
  { name: 'ARQ Python Worker Pool', role: 'Background Async Processing', port: 'Process Pool (4)', uptime: '99.95%', latency: '—', status: 'Healthy', icon: CpuIcon },
  { name: 'PostgreSQL Relational DB', role: 'Primary System Database', port: '5432', uptime: '100%', latency: '3ms', status: 'Healthy', icon: DatabaseIcon },
  { name: 'Redis Cache & Job Queue', role: 'In-Memory Store & Task Broker', port: '6379', uptime: '100%', latency: '< 1ms', status: 'Healthy', icon: DatabaseIcon },
  { name: 'MinIO S3 Storage', role: 'Object Storage for Satellites & Datasets', port: '9000', uptime: '99.99%', latency: '12ms', status: 'Healthy', icon: HardDriveIcon },
  { name: 'MLflow Model Registry', role: 'Model Tracking & Versioning', port: '5000', uptime: '99.90%', latency: '40ms', status: 'Healthy', icon: ActivityIcon },
  { name: 'Prometheus & Grafana', role: 'Metrics Monitoring & Dashboards', port: '9090 / 3001', uptime: '100%', latency: '15ms', status: 'Healthy', icon: BarChart2Icon },
  { name: 'Satellite Ingestion Stream', role: 'Himawari-8/9 NetCDF4 Feeder', port: 'Worker Process', uptime: '99.92%', latency: '210ms', status: 'Healthy', icon: RadioIcon },
];

export default function HealthPage() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600">
            <ActivityIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('health_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('health_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* System Metrics Cards */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
            <CpuIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-slate-600">{t('cpu_usage')}</p>
            <p className="text-[24px] font-bold text-ink">18.4%</p>
            <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full bg-blue-600" style={{ width: '18.4%' }} />
            </div>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-50 text-purple-600">
            <DatabaseIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-slate-600">{t('memory_ram')}</p>
            <p className="text-[24px] font-bold text-ink">4.2 <span className="text-[14px] font-normal text-muted">/ 16 GB</span></p>
            <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full bg-purple-600" style={{ width: '26.2%' }} />
            </div>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <HardDriveIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-slate-600">{t('disk_storage')}</p>
            <p className="text-[24px] font-bold text-ink">128 <span className="text-[14px] font-normal text-muted">/ 512 GB</span></p>
            <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full bg-amber-600" style={{ width: '25%' }} />
            </div>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <CheckCircle2Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-slate-600">{t('overall_status')}</p>
            <p className="text-[24px] font-bold text-ok">{t('all_systems_operational')}</p>
            <p className="text-[11.5px] text-muted">{t('services_normal_count')}</p>
          </div>
        </article>
      </div>

      {/* Services Grid */}
      <Panel title={t('microservices_status')} icon={<ServerIcon className="h-5 w-5 text-brand" />}>
        <div className="grid grid-cols-2 gap-3 mt-1">
          {infrastructureServices.map((s) => {
            const Icon = s.icon;
            return (
              <div key={s.name} className="flex items-center justify-between rounded-xl border border-line bg-canvas p-3.5">
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white border border-line shadow-2xs">
                    <Icon className="h-5 w-5 text-[#1e3a8a]" />
                  </span>
                  <div>
                    <h4 className="font-bold text-[14px] text-ink">{s.name}</h4>
                    <p className="text-[12px] text-slate-500">{s.role} • <span className="font-mono text-[11.5px] text-slate-600">Port {s.port}</span></p>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-right">
                  <div>
                    <p className="text-[12px] font-bold text-ink">{s.uptime}</p>
                    <p className="text-[11px] text-muted">{s.latency !== '—' ? `${s.latency}` : 'Active'}</p>
                  </div>
                  <span className="flex items-center gap-1.5 rounded-full bg-ok-soft px-2.5 py-1 text-[12px] font-bold text-ok">
                    <span className="h-2 w-2 rounded-full bg-ok animate-pulse" />
                    {s.status}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
