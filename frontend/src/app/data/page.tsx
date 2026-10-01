"use client";

import React from 'react';
import { DatabaseIcon, HardDriveIcon, RadioIcon, CloudDownloadIcon, CheckCircle2Icon, RefreshCwIcon, ServerIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';

const dataSources = [
  { name: 'Himawari-8/9 Satellite Feed', type: 'ภาพถ่ายดาวเทียมอินฟราเรด & แสงขาว', interval: 'ทุก 10 นาที', count: '144 เฟรม/วัน', size: '1.2 GB/วัน', status: 'กำลังซิงก์ข้อมูล', lastSync: '1 นาทีที่แล้ว' },
  { name: 'Ground Pyranometer Sensors', type: 'ค่าความเข้มรังสีดวงอาทิตย์ (GHI, DNI, DHI)', interval: 'ทุก 1 นาที', count: '7,200 เรคคอร์ด/วัน', size: '45 MB/วัน', status: 'ปกติ', lastSync: '30 วินาทีที่แล้ว' },
  { name: 'Solar Farm Inverter SCADA', type: 'กำลังไฟฟ้ากระแสตรง/สลับ, แรงดัน, กระแส', interval: 'ทุก 5 นาที', count: '1,440 เรคคอร์ด/วัน', size: '20 MB/วัน', status: 'ปกติ', lastSync: '2 นาทีที่แล้ว' },
  { name: 'TMD Weather Forecast Feed', type: 'อุณหภูมิ, ความชื้นสัมพัทธ์, ความเร็วลม', interval: 'ทุก 1 ชั่วโมง', count: '24 เรคคอร์ด/วัน', size: '5 MB/วัน', status: 'ปกติ', lastSync: '25 นาทีที่แล้ว' },
];

export default function DataPage() {
  const t = useTranslations('common');

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-600">
            <DatabaseIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('data_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('data_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Storage Highlights */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
            <HardDriveIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">MinIO S3 Storage</p>
            <p className="text-[24px] font-bold text-ink">458.4 <span className="text-[14px] font-normal text-muted">GB</span></p>
            <p className="text-[11.5px] text-muted">{t('storage_minio_desc')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
            <ServerIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">PostgreSQL DB</p>
            <p className="text-[24px] font-bold text-ink">2.4 <span className="text-[14px] font-normal text-muted">{t('million_rows')}</span></p>
            <p className="text-[11.5px] text-ok font-medium">{t('db_postgres_desc')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-50 text-purple-600">
            <RadioIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('data_rate')}</p>
            <p className="text-[24px] font-bold text-ink">99.8% <span className="text-[14px] font-normal text-ok">Uptime</span></p>
            <p className="text-[11.5px] text-muted">{t('packet_loss_zero')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <CloudDownloadIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('next_sync_round')}</p>
            <p className="text-[24px] font-bold text-ink">08:40 <span className="text-[14px] font-normal text-muted">น.</span></p>
            <p className="text-[11.5px] text-muted">{t('in_next_minutes')}</p>
          </div>
        </article>
      </div>

      {/* Data Sources Table */}
      <Panel
        title={t('data_pipelines')}
        icon={<DatabaseIcon className="h-5 w-5 text-brand" />}
        action={
          <button className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 hover:bg-canvas">
            <RefreshCwIcon className="h-3.5 w-3.5" />
            {t('sync_now')}
          </button>
        }
      >
        <div className="overflow-x-auto rounded-lg border border-line mt-1">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('data_source')}</th>
                <th className="px-4 py-3">{t('data_type')}</th>
                <th className="px-4 py-3 text-center">{t('record_frequency')}</th>
                <th className="px-4 py-3 text-center">{t('daily_volume')}</th>
                <th className="px-4 py-3 text-center">{t('file_size')}</th>
                <th className="px-4 py-3 text-center">{t('last_synced')}</th>
                <th className="px-4 py-3 text-center">{t('th_status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {dataSources.map((d) => (
                <tr key={d.name} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-bold text-ink">{d.name}</td>
                  <td className="px-4 py-3 text-slate-600">{d.type}</td>
                  <td className="px-4 py-3 text-center text-slate-600 font-medium">{d.interval}</td>
                  <td className="px-4 py-3 text-center text-slate-600 tabular-nums">{d.count}</td>
                  <td className="px-4 py-3 text-center text-slate-600 font-medium tabular-nums">{d.size}</td>
                  <td className="px-4 py-3 text-center text-muted tabular-nums">{d.lastSync}</td>
                  <td className="px-4 py-3 text-center">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-ok-soft px-2.5 py-1 text-[12px] font-bold text-ok">
                      <CheckCircle2Icon className="h-4 w-4" />
                      {d.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
