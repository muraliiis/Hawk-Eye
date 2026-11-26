import type {
  FleetCompliancePayload,
  NetworkPayload,
  ParkingSegment,
  PerceptionIngestRequest,
  PerceptionIngestResponse,
  RoadEventRecord,
  RoadSegment,
  RouteCompareResponse,
  SpeedAdvisory,
  WorkflowStatus,
} from './types';

export interface DashcamFeedItem {
  feed_id: string;
  title: string;
  source_label: string;
  url: string;
  default_segment_id: string;
}

export interface DashcamReplayCandidate {
  label: string;
  source_label: string;
  confidence: number;
  bbox_area_ratio: number;
  bbox_xyxy: [number, number, number, number];
  bbox_norm: [number, number, number, number];
}

export interface DashcamReplayVehicle {
  class_name: string;
  confidence: number;
  bbox_xyxy: [number, number, number, number];
  bbox_norm: [number, number, number, number];
  plate_blur_box_norm: [number, number, number, number];
}

export interface DashcamReplayResponse {
  model_version: string;
  inference_ms: number;
  image_size: [number, number];
  candidates: DashcamReplayCandidate[];
  vehicles: DashcamReplayVehicle[];
  published_events: RoadEventRecord[];
  frame_retained: false;
  dedup_window_seconds: number;
}

const API_BASE = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE || '';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = (await res.json()) as { detail?: string };
      if (data?.detail) detail = data.detail;
    } catch {
      // ignore non-json error body
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => requestJson<{ status: string; schema_version: string; event_count: number }>('/api/health'),

  getNetwork: () => requestJson<NetworkPayload>('/api/network'),

  listEvents: (params?: {
    category?: string;
    source_type?: string;
    status?: string;
    min_confidence?: number;
    segment_id?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set('category', params.category);
    if (params?.source_type) qs.set('source_type', params.source_type);
    if (params?.status) qs.set('status', params.status);
    if (params?.min_confidence !== undefined) qs.set('min_confidence', String(params.min_confidence));
    if (params?.segment_id) qs.set('segment_id', params.segment_id);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return requestJson<{ events: RoadEventRecord[]; count: number }>(`/api/events${suffix}`);
  },

  getDashcamFeeds: () => requestJson<{ feeds: DashcamFeedItem[] }>('/api/dashcam/feeds'),

  compareRoutes: (origin: string, destination: string) =>
    requestJson<RouteCompareResponse>('/api/routes/compare', {
      method: 'POST',
      body: JSON.stringify({ origin, destination }),
    }),

  getSpeedAdvisory: (payload: {
    legal_speed_limit_kph: number | null;
    hazard: string | null;
    distance_to_hazard_m: number | null;
  }) =>
    requestJson<SpeedAdvisory>('/api/routes/advisory', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  ingestPerception: (payload: PerceptionIngestRequest) =>
    requestJson<PerceptionIngestResponse>('/api/perception/ingest', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  analyzeReplayFrame: async (payload: {
    frame: Blob;
    roadSegmentId: string;
    frameTimestamp: Date;
    speedKph: number;
    confidenceThreshold?: number;
  }): Promise<DashcamReplayResponse> => {
    const form = new FormData();
    form.append('frame', payload.frame, 'dashcam-frame.jpg');
    form.append('road_segment_id', payload.roadSegmentId);
    form.append('frame_timestamp', payload.frameTimestamp.toISOString());
    form.append('speed_kph', String(payload.speedKph));
    if (payload.confidenceThreshold !== undefined) {
      form.append('confidence_threshold', String(payload.confidenceThreshold));
    }
    const res = await fetch(`${API_BASE}/api/perception/replay-frame`, { method: 'POST', body: form });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const data = (await res.json()) as { detail?: string };
        if (data.detail) detail = data.detail;
      } catch {
        // ignore non-json error body
      }
      throw new Error(detail);
    }
    return (await res.json()) as DashcamReplayResponse;
  },

  sendDriverFeedback: (eventId: string, action: 'confirm' | 'cleared') =>
    requestJson<{ event: RoadEventRecord }>(`/api/events/${eventId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),

  moderateEvent: (eventId: string, workflow_status: WorkflowStatus, severity?: 'low' | 'medium' | 'high') =>
    requestJson<{ event: RoadEventRecord }>(`/api/admin/events/${eventId}`, {
      method: 'PATCH',
      body: JSON.stringify({ workflow_status, severity }),
    }),

  updateSegment: (
    segmentId: string,
    payload: {
      closed?: boolean;
      extra_hazard_penalty?: number;
      mean_speed_kph?: number;
      vehicle_count?: number;
    },
  ) =>
    requestJson<{ segment: RoadSegment; emitted_congestion_event: RoadEventRecord | null }>(
      `/api/admin/segments/${segmentId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    ),

  getParking: () => requestJson<{ segments: ParkingSegment[]; count: number }>('/api/parking'),

  getFleet: () => requestJson<FleetCompliancePayload>('/api/admin/fleet'),

  simulateBurst: () =>
    requestJson<PerceptionIngestResponse>('/api/admin/simulate-burst', {
      method: 'POST',
    }),
};

export function subscribeRoadStream(
  onUpdate: (eventType: string) => void,
  onStatus?: (connected: boolean) => void,
): () => void {
  const source = new EventSource(`${API_BASE}/api/stream`);

  source.addEventListener('connected', () => onStatus?.(true));
  source.addEventListener('event_created', () => onUpdate('event_created'));
  source.addEventListener('event_updated', () => onUpdate('event_updated'));
  source.addEventListener('segment_updated', () => onUpdate('segment_updated'));
  source.onerror = () => {
    onStatus?.(false);
  };

  return () => {
    source.close();
  };
}
