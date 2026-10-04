const CLOCK_FORMAT = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'Asia/Bangkok', // all SolarDSS stations are in Thailand
});

/** Parse an ISO string from the backend; timestamps without a zone are treated as UTC. */
export function parseBackendDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Wall-clock label (HH:mm, Thailand time) of forecast step `step`
 * (1 = first step after `baseIso`). Falls back to "+Nm" if the base time is unknown.
 */
export function forecastTimeLabel(baseIso: string | undefined | null, step: number, stepMinutes = 10): string {
  const base = parseBackendDate(baseIso);
  if (!base) return `+${step * stepMinutes}m`;
  // Snap to the model's grid so labels read 08:50, 09:00 ... instead of 08:53, 09:03 ...
  const stepMs = stepMinutes * 60_000;
  const snapped = Math.floor(base.getTime() / stepMs) * stepMs;
  return CLOCK_FORMAT.format(new Date(snapped + step * stepMs));
}
