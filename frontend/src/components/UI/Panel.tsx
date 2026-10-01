import React from 'react';

type PanelProps = {
  title: string;
  icon: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

export function Panel({ title, icon, action, className = '', children }: PanelProps) {
  return (
    <section className={`flex min-h-0 flex-col rounded-xl border border-line bg-white p-3.5 shadow-[0_1px_3px_rgba(15,23,42,0.06)] ${className}`}>
      <header className="mb-2.5 flex shrink-0 items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-5 w-5 items-center justify-center">{icon}</span>
          <h2 className="whitespace-nowrap text-[15.5px] font-bold text-ink">{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>);

}