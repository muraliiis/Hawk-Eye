import axios from 'axios';
import type { RoadEvent, ParkingObservation, RouteOption, GPSCoord, BBox, RouteCompareRequest } from '@/types';

const API_ORIGIN = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

const client = axios.create({
  baseURL: API_ORIGIN,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API error:', error.response?.status, error.response?.data);
    return Promise.reject(error);
  }
);

// ─── Road Events ─────────────────────────────────────────────────────────────

/** GET /api/events — in-memory store, real-time, supports bbox filter */
export async function fetchRoadEvents(
  bbox?: BBox,
  eventType?: string
): Promise<RoadEvent[]> {
  const params: Record<string, string | number> = {};
  if (bbox) {
    params['min_lat'] = bbox.min_lat;
    params['min_lon'] = bbox.min_lon;
    params['max_lat'] = bbox.max_lat;
    params['max_lon'] = bbox.max_lon;
  }
  if (eventType) params['event_type'] = eventType;
  const { data } = await client.get<RoadEvent[]>('/api/events', { params });
  return data;
}

/** GET /api/v1/events/nearby — DB-backed, paginated proximity search */
export async function fetchNearbyEvents(
  lat: number,
  lon: number,
  radius = 1000
): Promise<RoadEvent[]> {
  const { data } = await client.get<RoadEvent[]>('/api/v1/events/nearby', {
    params: { lat, lon, radius },
  });
  return data;
}

// ─── Parking ─────────────────────────────────────────────────────────────────

/** GET /api/v1/parking/availability — DB-backed */
export async function fetchParkingAvailability(
  lat: number,
  lon: number,
  radius = 500
): Promise<ParkingObservation[]> {
  const { data } = await client.get<ParkingObservation[]>('/api/v1/parking/availability', {
    params: { lat, lon, radius },
  });
  return data;
}

// ─── Route Options ────────────────────────────────────────────────────────────

/** POST /api/routes/compare — in-memory store, expects "lat,lon" string coords */
export async function fetchRouteOptions(
  origin: GPSCoord,
  destination: GPSCoord
): Promise<RouteOption[]> {
  const body: RouteCompareRequest = {
    origin: `${origin.lat},${origin.lon}`,
    destination: `${destination.lat},${destination.lon}`,
  };
  const { data } = await client.post<RouteOption[]>('/api/routes/compare', body);
  return data;
}

// ─── Telemetry ────────────────────────────────────────────────────────────────

/** POST /api/v1/ingest/telemetry — DB-backed */
export async function ingestTelemetry(payload: unknown): Promise<void> {
  await client.post('/api/v1/ingest/telemetry', payload);
}

// ─── SSE Stream ───────────────────────────────────────────────────────────────

/** Returns an EventSource connected to /api/stream (in-memory, real-time SSE) */
export function subscribeToEvents(onEvent: (data: unknown) => void): EventSource {
  const es = new EventSource(`${API_ORIGIN}/api/stream`);
  es.onmessage = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data as string));
    } catch {
      onEvent(e.data);
    }
  };
  return es;
}

export default client;
