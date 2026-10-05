import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CloudIcon,
  CloudSunIcon,
  EyeIcon,
  MoonIcon,
  ShieldAlertIcon,
  SunIcon,
  type LucideIcon,
} from 'lucide-react';
import type { AlertLevel, CloudImpactLevel } from '@/services/api';

export type Tone = 'ok' | 'warn' | 'bad' | 'muted';

/** Status colours are reserved for these states and always shown with an icon and a label. */
export const TONE_CLASS: Record<Tone, { box: string; icon: string; chip: string; fill: string }> = {
  ok: { box: 'border-ok/30 bg-ok-soft', icon: 'text-ok', chip: 'bg-ok-soft text-[#166534]', fill: '#16a34a' },
  warn: { box: 'border-warn/30 bg-warn-soft', icon: 'text-warn', chip: 'bg-warn-soft text-[#92400e]', fill: '#d97706' },
  bad: { box: 'border-bad/30 bg-bad-soft', icon: 'text-bad', chip: 'bg-bad-soft text-[#991b1b]', fill: '#dc2626' },
  muted: { box: 'border-line bg-slate-50', icon: 'text-slate-500', chip: 'bg-slate-100 text-slate-700', fill: '#94a3b8' },
};

type AlertKey = 'alert_night' | 'alert_normal' | 'alert_watch' | 'alert_warning' | 'alert_critical';

export const ALERT_UI: Record<AlertLevel, { tone: Tone; icon: LucideIcon; labelKey: AlertKey }> = {
  night: { tone: 'muted', icon: MoonIcon, labelKey: 'alert_night' },
  normal: { tone: 'ok', icon: CheckCircle2Icon, labelKey: 'alert_normal' },
  watch: { tone: 'warn', icon: EyeIcon, labelKey: 'alert_watch' },
  warning: { tone: 'warn', icon: AlertTriangleIcon, labelKey: 'alert_warning' },
  critical: { tone: 'bad', icon: ShieldAlertIcon, labelKey: 'alert_critical' },
};

export function alertUi(level: string | null | undefined) {
  return ALERT_UI[(level ?? '') as AlertLevel] ?? null;
}

type CloudKey = 'cloud_low' | 'cloud_medium' | 'cloud_high';

export const CLOUD_UI: Record<CloudImpactLevel, { tone: Tone; icon: LucideIcon; labelKey: CloudKey }> = {
  low: { tone: 'ok', icon: SunIcon, labelKey: 'cloud_low' },
  medium: { tone: 'warn', icon: CloudSunIcon, labelKey: 'cloud_medium' },
  high: { tone: 'bad', icon: CloudIcon, labelKey: 'cloud_high' },
};

/** Cloud cover in the area around the station, in %, at which GHI is expected to drop by 10% and 30% (Kasten & Czeplak 1980). */
export const CLOUD_MEDIUM_FROM_PCT = 55;
export const CLOUD_HIGH_FROM_PCT = 76;

export function cloudLevelOf(pct: number | null | undefined): CloudImpactLevel | null {
  if (pct === null || pct === undefined) return null;
  if (pct >= CLOUD_HIGH_FROM_PCT) return 'high';
  if (pct >= CLOUD_MEDIUM_FROM_PCT) return 'medium';
  return 'low';
}
