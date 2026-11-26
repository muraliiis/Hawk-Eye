// ─── Enums ────────────────────────────────────────────────────────────────────

export enum RoadEventType {
  POTHOLE        = 'POTHOLE',
  ROAD_DAMAGE    = 'ROAD_DAMAGE',
  CONSTRUCTION   = 'CONSTRUCTION',
  WATERLOGGING   = 'WATERLOGGING',
  OBSTACLE       = 'OBSTACLE',
  SPEED_BREAKER  = 'SPEED_BREAKER',
  SIGNAL         = 'SIGNAL',
  SIGN           = 'SIGN',
}

export enum RouteScoringType {
  FASTEST   = 'FASTEST',
  SAFEST    = 'SAFEST',
  SMOOTHEST = 'SMOOTHEST',
  BALANCED  = 'BALANCED',
}

export enum SeverityLevel {
  LOW      = 'LOW',
  MEDIUM   = 'MEDIUM',
  HIGH     = 'HIGH',
  CRITICAL = 'CRITICAL',
}

// ─── Core Types ───────────────────────────────────────────────────────────────

export interface GPSCoord {
  lat: number;
  lon: number;
  altitude?: number;
  accuracy?: number;
}

export interface RoadEvent {
  id: string;
  event_type: RoadEventType;
  category?: string;           // from in-memory store
  severity: SeverityLevel;
  confidence: number;          // 0–1
  // Flat coords returned by backend
  lat?: number;
  lon?: number;
  // Nested coord object (kept for UI compatibility)
  location?: GPSCoord;
  is_active?: boolean;
  observed_at?: string;        // ISO datetime — DB-backed routes
  created_at?: string;
  reported_at?: string;        // ISO-8601 — legacy / in-memory routes
  expires_at?: string;
  source?: string;
  road_segment_id?: string;
  segment_id?: string;
  vehicle_speed?: number;
  gps_accuracy?: number;
  verification_count?: number;
  description?: string;
  metadata?: Record<string, unknown>;
}

export interface ParkingObservation {
  id: string;
  segment_id: string;
  segment_name?: string;
  location: GPSCoord;
  occupancy_rate: number;      // 0–1
  total_spaces?: number;
  occupied_spaces?: number;
  observed_at: string;         // ISO-8601
  source?: string;
}

export interface RouteOption {
  id: string;
  scoring_type: RouteScoringType;
  polyline: GPSCoord[];
  distance_km: number;
  estimated_time_min: number;
  road_quality_score: number;  // 0–10
  hazard_count: number;
  congestion_level: number;    // 0–1
  waypoints?: GPSCoord[];
  metadata?: Record<string, unknown>;
}

export interface HazardAlert {
  id: string;
  event_id?: string;
  message: string;
  severity: SeverityLevel;
  location?: GPSCoord;
  created_at: string;
  expires_at?: string;
}

export interface TrafficSegment {
  id: string;
  name: string;
  start: GPSCoord;
  end: GPSCoord;
  quality_score: number;       // 0–10
  pothole_density: number;     // potholes / km
  speed_limit_kmh?: number;
  current_speed_kmh?: number;
  congestion_level: number;    // 0–1
}

export interface SpeedAdvisory {
  segment_id?: string;
  current_speed_kmh: number;
  speed_limit_kmh: number;
  advisory_speed_kmh: number;
  reason?: string;
  hazard_ahead: boolean;
  hazard_distance_m?: number;
}

// ─── API Utility Types ────────────────────────────────────────────────────────

export type BBox = {
  min_lat: number;
  min_lon: number;
  max_lat: number;
  max_lon: number;
};

export interface BBoxNamed {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}

export interface RouteCompareRequest {
  origin: string;        // "lat,lon" format
  destination: string;   // "lat,lon" format
}

export interface SSEEvent {
  type: string;
  payload: unknown;
}
