import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export interface SatelliteFrameDto {
  frame_no: number;
  timestamp: string;
  image_url: string;
  time_label: string;
  source: string;
}

const NICT_LATEST_JSON = 'https://himawari8-dl.nict.go.jp/himawari8/img/D531106/latest.json';
const NICT_BASE_IMG_URL = 'https://himawari8-dl.nict.go.jp/himawari8/img/D531106';

function formatNictImageUrl(date: Date): string {
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(date.getUTCDate()).padStart(2, '0');
  const hh = String(date.getUTCHours()).padStart(2, '0');
  const min = String(date.getUTCMinutes()).padStart(2, '0');
  const ss = String(date.getUTCSeconds()).padStart(2, '0');
  return `${NICT_BASE_IMG_URL}/1d/550/${yyyy}/${mm}/${dd}/${hh}${min}${ss}_0_0.png`;
}

function formatTimeLabel(date: Date): string {
  // Format in UTC and Thai Local Time (UTC+7)
  const utcHours = String(date.getUTCHours()).padStart(2, '0');
  const utcMinutes = String(date.getUTCMinutes()).padStart(2, '0');

  const thaiDate = new Date(date.getTime() + 7 * 60 * 60 * 1000);
  const thaiHours = String(thaiDate.getUTCHours()).padStart(2, '0');
  const thaiMinutes = String(thaiDate.getUTCMinutes()).padStart(2, '0');

  return `${thaiHours}:${thaiMinutes} น. (${utcHours}:${utcMinutes} UTC)`;
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const count = Math.min(48, Math.max(1, parseInt(searchParams.get('count') || '12', 10)));
  const stationId = searchParams.get('station_id') || 'ST-001';

  // 1. Try Backend API first (if backend ingestion endpoint is active)
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  try {
    const authHeader = req.headers.get('authorization');
    const headers: Record<string, string> = {};
    if (authHeader) headers['Authorization'] = authHeader;

    const backendRes = await fetch(`${backendUrl}/api/ingestion/satellite/${stationId}/frames?count=${count}`, {
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(2000),
    });

    if (backendRes.ok) {
      const data = await backendRes.json();
      if (Array.isArray(data) && data.length > 0) {
        const mappedFrames: SatelliteFrameDto[] = data.map(
          (item: { frame_no?: number; timestamp?: string; image_url?: string }, idx: number) => {
            const rawUrl = item.image_url || '';
          const finalUrl = rawUrl.startsWith('http') ? rawUrl : `${backendUrl}${rawUrl}`;
          const dt = new Date(item.timestamp || Date.now());
          return {
            frame_no: item.frame_no || idx + 1,
            timestamp: dt.toISOString(),
            image_url: finalUrl,
            time_label: formatTimeLabel(dt),
            source: 'backend_storage',
          };
        });

        return NextResponse.json({
          status: 'success',
          source: 'backend',
          total_frames: mappedFrames.length,
          latest_frame: mappedFrames[mappedFrames.length - 1],
          frames: mappedFrames,
        });
      }
    }
  } catch {
    // Backend offline or timeout -> proceed seamlessly to direct Himawari-8/9 NICT feeder
  }

  // 2. Fetch latest real-time frame from Himawari-8/9 (NICT Japan)
  let latestDt: Date | null = null;
  try {
    const nictRes = await fetch(NICT_LATEST_JSON, {
      headers: { 'User-Agent': 'SolarForecastDSS/1.0' },
      cache: 'no-store',
      signal: AbortSignal.timeout(4000),
    });

    if (nictRes.ok) {
      const nictData = await nictRes.json();
      if (nictData?.date) {
        // e.g. "2026-10-01 14:50:00" in UTC
        latestDt = new Date(`${nictData.date.replace(' ', 'T')}Z`);
      }
    }
  } catch (err) {
    console.warn('[Satellite Route] NICT latest.json unreachable, approximating latest frame:', err);
  }

  // If latestDt could not be fetched from NICT, approximate from current UTC time (typically ~20 mins lag)
  if (!latestDt || isNaN(latestDt.getTime())) {
    const now = new Date();
    const approx = new Date(now.getTime() - 20 * 60 * 1000);
    const minuteFloor = Math.floor(approx.getUTCMinutes() / 10) * 10;
    latestDt = new Date(Date.UTC(
      approx.getUTCFullYear(),
      approx.getUTCMonth(),
      approx.getUTCDate(),
      approx.getUTCHours(),
      minuteFloor,
      0
    ));
  }

  // 3. Build sequence of consecutive 10-minute frames ending at latestDt
  const frames: SatelliteFrameDto[] = [];
  for (let i = count - 1; i >= 0; i--) {
    const frameDate = new Date(latestDt.getTime() - i * 10 * 60 * 1000);
    frames.push({
      frame_no: count - i,
      timestamp: frameDate.toISOString(),
      image_url: formatNictImageUrl(frameDate),
      time_label: formatTimeLabel(frameDate),
      source: 'nict_himawari9',
    });
  }

  return NextResponse.json(
    {
      status: 'success',
      source: 'nict_himawari9',
      station_id: stationId,
      total_frames: frames.length,
      latest_frame: frames[frames.length - 1],
      frames,
    },
    {
      headers: {
        'Cache-Control': 'public, s-maxage=60, stale-while-revalidate=120',
      },
    }
  );
}
