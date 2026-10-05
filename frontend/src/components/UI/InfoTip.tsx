"use client";

import React, { useId } from 'react';
import { HelpCircleIcon } from 'lucide-react';

/** Small "?" next to an abbreviation: the explanation shows on hover and on keyboard focus. */
export function InfoTip({ text, align = 'left' }: { text: string; align?: 'left' | 'right' }) {
  const id = useId();
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-describedby={id}
        className="flex h-5 w-5 items-center justify-center rounded-full text-slate-400 hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-mid"
      >
        <HelpCircleIcon className="h-4 w-4" aria-hidden="true" />
        <span className="sr-only">{text}</span>
      </button>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute top-6 z-30 hidden w-64 rounded-lg border border-line bg-white px-3 py-2 text-left text-[12.5px] font-normal leading-snug text-slate-700 shadow-lg group-focus-within:block group-hover:block ${
          align === 'right' ? 'right-0' : 'left-0'
        }`}
      >
        {text}
      </span>
    </span>
  );
}
