"use client";

import React, { useState } from 'react';
import { ListChecksIcon, PlayIcon, CheckCircle2Icon, ClockIcon, RotateCwIcon, ServerCogIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';

const initialJobs = [
  { id: 'job_001', name: 'sync_himawari_satellite_images', queue: 'satellite_queue', schedule: 'ทุก 10 นาที', lastRun: '19:40:00 น.', duration: '14.2s', status: 'Success' },
  { id: 'job_002', name: 'infer_convlstm_cloud_motion', queue: 'ai_inference_queue', schedule: 'ทุก 15 นาที', lastRun: '19:45:00 น.', duration: '2.8s', status: 'Running' },
  { id: 'job_003', name: 'predict_bilstm_ghi_forecast', queue: 'ai_inference_queue', schedule: 'ทุก 15 นาที', lastRun: '19:45:03 น.', duration: '1.4s', status: 'Success' },
  { id: 'job_004', name: 'evaluate_decision_curtailment_alert', queue: 'default_queue', schedule: 'ทุก 5 นาที', lastRun: '19:45:10 น.', duration: '0.6s', status: 'Success' },
  { id: 'job_005', name: 'nightly_model_retrain_benchmark', queue: 'batch_training_queue', schedule: 'ทุกวัน เวลา 02:00 น.', lastRun: '30 ก.ย. 02:00 น.', duration: '42m 18s', status: 'Scheduled' },
  { id: 'job_006', name: 'archive_telemetry_to_minio', queue: 'maintenance_queue', schedule: 'ทุกอาทิตย์ เวลา 00:00 น.', lastRun: '28 ก.ย. 00:00 น.', duration: '3m 12s', status: 'Scheduled' },
];

export default function JobsPage() {
  const t = useTranslations('common');
  const [jobs, setJobs] = useState(initialJobs);

  const runJob = (id: string) => {
    setJobs(jobs.map(j => j.id === id ? { ...j, status: 'Running' } : j));
    setTimeout(() => {
      setJobs(jobs => jobs.map(j => j.id === id ? { ...j, status: 'Success', lastRun: 'เมื่อสักครู่' } : j));
    }, 2000);
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
            <ListChecksIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('jobs_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('jobs_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
            <ServerCogIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('workers_active')}</p>
            <p className="text-[24px] font-bold text-ink">4 / 4 <span className="text-[14px] font-normal text-ok">{t('online')}</span></p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <CheckCircle2Icon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('jobs_completed_today')}</p>
            <p className="text-[24px] font-bold text-ink">1,248 <span className="text-[14px] font-normal text-muted">{t('unit_jobs')}</span></p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-50 text-purple-600">
            <RotateCwIcon className="h-5 w-5 animate-spin" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('running_jobs')}</p>
            <p className="text-[24px] font-bold text-purple-600">1 <span className="text-[14px] font-normal text-muted">{t('unit_jobs')}</span></p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-600">
            <ClockIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('scheduled_jobs')}</p>
            <p className="text-[24px] font-bold text-ink">2 <span className="text-[14px] font-normal text-muted">{t('unit_jobs')}</span></p>
          </div>
        </article>
      </div>

      {/* Main Jobs Table */}
      <Panel title={t('task_queue_list')} icon={<ListChecksIcon className="h-5 w-5 text-brand" />}>
        <div className="overflow-x-auto rounded-lg border border-line mt-1">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('job_id')}</th>
                <th className="px-4 py-3">{t('task_name')}</th>
                <th className="px-4 py-3">{t('queue')}</th>
                <th className="px-4 py-3">{t('schedule')}</th>
                <th className="px-4 py-3 text-center">{t('last_run')}</th>
                <th className="px-4 py-3 text-center">{t('duration')}</th>
                <th className="px-4 py-3 text-center">{t('th_status')}</th>
                <th className="px-4 py-3 text-center">{t('action_execution')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {jobs.map((j) => (
                <tr key={j.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-mono text-[12px] text-slate-500">{j.id}</td>
                  <td className="px-4 py-3 font-bold text-ink font-mono text-[12.5px]">{j.name}</td>
                  <td className="px-4 py-3 text-slate-600">
                    <span className="rounded bg-canvas px-2 py-0.5 text-[11.5px] font-mono border border-line">
                      {j.queue}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600 font-medium">{j.schedule}</td>
                  <td className="px-4 py-3 text-center text-slate-600 tabular-nums">{j.lastRun}</td>
                  <td className="px-4 py-3 text-center text-muted tabular-nums">{j.duration}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11.5px] font-bold ${
                      j.status === 'Success' ? 'bg-ok-soft text-ok' :
                      j.status === 'Running' ? 'bg-purple-100 text-purple-700' : 'bg-canvas text-slate-600 border border-line'
                    }`}>
                      {j.status === 'Running' && <span className="h-2 w-2 rounded-full bg-purple-600 animate-ping" />}
                      {j.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => runJob(j.id)}
                      disabled={j.status === 'Running'}
                      className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2.5 py-1 text-[12px] font-semibold text-slate-700 hover:bg-canvas disabled:opacity-50"
                    >
                      <PlayIcon className="h-3 w-3 fill-slate-700" />
                      {t('run_now')}
                    </button>
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
