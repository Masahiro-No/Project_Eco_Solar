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

/** Expected loss of irradiance (%) at which the impact level changes (same limits as the backend). */
export const LOSS_MEDIUM_FROM_PCT = 10;
export const LOSS_HIGH_FROM_PCT = 30;

export function impactLevelOfLoss(lossPct: number | null | undefined): CloudImpactLevel | null {
  if (lossPct === null || lossPct === undefined) return null;
  if (lossPct > LOSS_HIGH_FROM_PCT) return 'high';
  if (lossPct >= LOSS_MEDIUM_FROM_PCT) return 'medium';
  return 'low';
}

/** Status codes of the satellite branch of a forecast round (same names as the backend). */
export const SATELLITE_STATUSES = ['ok', 'shifted', 'observed_only', 'missing', 'low_sun', 'night', 'model_unavailable'] as const;
export type SatelliteStatusCode = (typeof SATELLITE_STATUSES)[number];
export const isSatelliteStatus = (s: string | null | undefined): s is SatelliteStatusCode =>
  !!s && (SATELLITE_STATUSES as readonly string[]).includes(s);
