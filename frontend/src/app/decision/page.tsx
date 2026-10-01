"use client";

import React, { useState } from 'react';
import { LightbulbIcon, ShieldAlertIcon, CheckCircle2Icon, PlayIcon, RefreshCwIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { DecisionSupport } from '@/components/UI/DecisionSupport';
import { DecisionLog } from '@/components/UI/DecisionLog';
import { Panel } from '@/components/UI/Panel';

const initialRecommendations = [
  { id: 1, action: 'สั่งสตาร์ทเครื่องกำเนิดไฟฟ้าสำรอง (Spinning Reserve)', station: 'Hat Yai Solar Farm', impact: '+120 kW', priority: 'High', status: 'pending', reason: 'เมฆหนาเคลื่อนตัวเข้าใน 30 นาทีข้างหน้า' },
  { id: 2, action: 'ปรับลดเป้าหมายการจ่ายไฟเข้าระบบ (Curtailment Target)', station: 'Songkhla Solar Farm', impact: '-50 kW', priority: 'Medium', status: 'executed', reason: 'ค่า GHI ต่ำกว่าเกณฑ์มาตรฐาน 15%' },
  { id: 3, action: 'เริ่มเก็บประจุแบตเตอรี่สำรอง (BESS Charge)', station: 'Nakhon Si Thammarat Solar Farm', impact: '+80 kW', priority: 'Low', status: 'executed', reason: 'กำลังการผลิตเกินเป้าหมาย 30 kW' },
];

export default function DecisionPage() {
  const t = useTranslations('common');
  const [items, setItems] = useState(initialRecommendations);

  const handleConfirm = (id: number) => {
    setItems(items.map(item => item.id === id ? { ...item, status: 'executed' } : item));
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
            <LightbulbIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">{t('decision_page_title')}</h1>
            <p className="text-[13.5px] text-slate-600">{t('decision_page_desc')}</p>
          </div>
        </div>
      </div>

      {/* Top Support Panels */}
      <div className="grid grid-cols-2 gap-3.5">
        <DecisionSupport />
        <DecisionLog />
      </div>

      {/* Actionable Recommendations Table */}
      <Panel
        title={t('action_recommendations')}
        icon={<ShieldAlertIcon className="h-5 w-5 text-brand" />}
        action={
          <button className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 hover:bg-canvas">
            <RefreshCwIcon className="h-3.5 w-3.5" />
            {t('recalculate')}
          </button>
        }
      >
        <div className="overflow-x-auto rounded-lg border border-line mt-1">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('th_id')}</th>
                <th className="px-4 py-3">{t('action_plan')}</th>
                <th className="px-4 py-3">{t('target_station')}</th>
                <th className="px-4 py-3 text-center">{t('impact')}</th>
                <th className="px-4 py-3 text-center">{t('priority')}</th>
                <th className="px-4 py-3">{t('technical_reason')}</th>
                <th className="px-4 py-3 text-center">{t('action_execution')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {items.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-semibold text-slate-500">{r.id}</td>
                  <td className="px-4 py-3 font-bold text-ink">{r.action}</td>
                  <td className="px-4 py-3 text-slate-600 font-medium">{r.station}</td>
                  <td className="px-4 py-3 text-center font-bold text-brand tabular-nums">{r.impact}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-bold ${
                      r.priority === 'High' ? 'bg-bad-soft text-bad' :
                      r.priority === 'Medium' ? 'bg-warn-soft text-warn' : 'bg-ok-soft text-ok'
                    }`}>
                      {r.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600 max-w-xs truncate">{r.reason}</td>
                  <td className="px-4 py-3 text-center">
                    {r.status === 'pending' ? (
                      <button
                        onClick={() => handleConfirm(r.id)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-[12px] font-bold text-white shadow-sm hover:bg-brand/90 transition-colors"
                      >
                        <PlayIcon className="h-3.5 w-3.5 fill-white" />
                        {t('confirm_order')}
                      </button>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[12px] font-bold text-ok">
                        <CheckCircle2Icon className="h-4 w-4" />
                        {t('executed')}
                      </span>
                    )}
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
