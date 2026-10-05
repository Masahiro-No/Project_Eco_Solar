/**
 * Frame review API client: human check of the real satellite frames the ConvLSTM is retrained on.
 * Matches backend: api/frame_review/schema.py
 */
import { send } from './labelingApi';

export type ReviewStatus = 'rejected' | 'accepted';
export type ReviewReason = 'blank' | 'partial' | 'artifact' | 'glare' | 'other';
export type FrameFlag = 'blank' | 'partial' | 'saturated' | 'jump';

export interface FrameReview {
  status: ReviewStatus;
  reason: string | null;
  reviewed_by: string;
  reviewed_at: string | null;
}

export interface FrameItem {
  timestamp: string; // scan time, ISO (UTC)
  cloud_pct: number | null;
  brightness: number;
  flags: FrameFlag[];
  image_b64: string;
  review: FrameReview | null;
}

export interface FrameListResponse {
  station_id: string;
  date: string;
  daytime_frames: number;
  night_frames: number;
  flagged: number;
  rejected: number;
  frames: FrameItem[];
}

export interface ReviewItem {
  timestamp: string;
  status: ReviewStatus;
  reason?: ReviewReason;
}

export interface SubmitReviewsResponse {
  station_id: string;
  saved: number;
  rejected: number;
  accepted: number;
}

export interface ConvLstmRunMetrics {
  mse: number;
  ssim: number;
  aoi_cloud_mae_pct: number;
}

export interface ConvLstmStatus {
  retrain_enabled: boolean;
  batch_size: number | null;
  new_scans: number | null;
  newest_scan: string | null;
  checked_at: string | null;
  model_version: string | null;
  retrained_at: string | null;
  last_result: {
    status: string;
    reason?: string;
    version?: string;
    train_sequences?: number;
    val_sequences?: number;
    frames_rejected_by_review?: number;
    baseline?: ConvLstmRunMetrics;
    candidate?: ConvLstmRunMetrics;
    finished_at?: string;
  } | null;
  rejected_frames_total: number;
}

export const frameReviewApi = {
  getFrames(stationId: string, date: string): Promise<FrameListResponse> {
    const q = new URLSearchParams({ station_id: stationId, date });
    return send(`/api/frame-review/frames?${q.toString()}`, { method: 'GET' }, true);
  },

  submit(stationId: string, items: ReviewItem[]): Promise<SubmitReviewsResponse> {
    return send('/api/frame-review/frames', { method: 'POST', body: JSON.stringify({ station_id: stationId, items }) }, true);
  },

  getStatus(): Promise<ConvLstmStatus> {
    return send('/api/frame-review/status', { method: 'GET' }, true);
  },
};
