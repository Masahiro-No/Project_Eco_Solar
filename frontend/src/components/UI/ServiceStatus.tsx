"use client";

import React from 'react';
import { ServerCogIcon, CheckIcon, XIcon } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from './Panel';
import { services } from '@/data/dashboard';

export function ServiceStatus() {
  const t = useTranslations('common');

  return (
    <Panel
      title={t('services_status_title')}
      icon={<ServerCogIcon className="h-5 w-5 text-[#1e3a8a]" />}
      className="shrink-0"
    >
      <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
        {services.map((s) => (
          <li key={s.id} className="flex items-center gap-2.5 whitespace-nowrap text-[12.5px] font-medium text-ink">
            <span
              className={`flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full ${
                s.ok ? 'bg-ok' : 'bg-bad'
              }`}
            >
              {s.ok ? (
                <CheckIcon className="h-3 w-3 text-white" strokeWidth={3} />
              ) : (
                <XIcon className="h-3 w-3 text-white" strokeWidth={3} />
              )}
            </span>
            {s.name}
          </li>
        ))}
      </ul>
    </Panel>
  );
}