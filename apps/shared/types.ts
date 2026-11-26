export type EventCategory =
  | 'pothole'
  | 'crack'
  | 'uneven_surface'
  | 'speed_breaker'
  | 'obstacle'
  | 'waterlogging'
  | 'construction'
  | 'road_closure'
  | 'traffic_congestion'
  | 'incident'
  | 'speed_limit_sign';

export type SourceType =
  | 'camera_observed'
  | 'sensor_observed'
  | 'telemetry_aggregated'
  | 'external_provider'
  | 'inferred';

export type WorkflowStatus = 'active' | 'verified' | 'resolved' | 'dismissed';

export type RouteProfile = 'balanced' | 'safest' | 'smoothest' | 'fastest';

export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export interface RoadEventRecord {
  schema_version: string;
  event_id: string;
  category: EventCategory;
  source_type: SourceType;
  observed_at: string;
  location: GeoPoint;
  location_accuracy_m: number;
  confidence: number;
  road_segment_id: string | null;
  attributes: Record<string, unknown>;
  workflow_status: WorkflowStatus;
  confirmations: number;
  dismissals: number;
}

export interface GraphNode {
  id: string;
  name: string;
  area: string;
  latitude: number;
  longitude: number;
}

export interface SegmentTrafficState {
  road_segment_id: string;
  mean_speed_kph: number;
  free_flow_speed_kph: number;
  vehicle_count: number;
  congestion_ratio: number;
  is_congested: boolean;
}

export interface RoadSegment {
  segment_id: string;
  name: string;
  start: string;
  end: string;
  distance_km: number;
  base_travel_minutes: number;
  legal_speed_limit_kph: number;
  free_flow_speed_kph: number;
  polyline: [number, number][];
  closed: boolean;
  road_quality_penalty: number;
  hazard_penalty: number;
  congestion_penalty: number;
  traffic: SegmentTrafficState;
}

export interface NetworkPayload {
  nodes: GraphNode[];
  segments: RoadSegment[];
}

export interface RouteComparisonItem {
  profile: RouteProfile;
  nodes: string[];
  node_names: string[];
  segment_ids: string[];
  polyline: [number, number][];
  score: number;
  distance_km: number;
  travel_minutes: number;
  road_quality_score: number;
  hazard_count: number;
  default_legal_speed_limit_kph: number;
  events: RoadEventRecord[];
  explanation: string;
  /** `road-network` is safe to draw as a driving route; fallback is explicitly flagged in the UI. */
  geometry_source?: 'road-network' | 'seed-fallback';
}

export interface RouteCompareResponse {
  origin: string;
  destination: string;
  routes: RouteComparisonItem[];
}

export interface SpeedAdvisory {
  advisory_speed_kph: number;
  legal_speed_limit_kph: number | null;
  reason: string;
}

export interface ParkingSegment {
  road_segment_id: string;
  segment_name: string;
  area: string;
  total_spaces_estimated: number;
  occupied_spaces: number;
  available_spaces: number;
  occupancy_rate: number;
  confidence: number;
  history_window_size: number;
  last_observed: string;
  center: GeoPoint;
  polyline: [number, number][];
  privacy_masked: boolean;
}

export interface EdgeUnit {
  unit_id: string;
  vehicle_label: string;
  corridor: string;
  status: 'online' | 'degraded' | 'offline';
  latitude: number;
  longitude: number;
  gnss_age_ms: number;
  gnss_max_alignment_ms: number;
  gnss_accuracy_m: number;
  imu_harsh_brakes_1h: number;
  model_version: string;
  fps: number;
  parking_every_n: number;
  anpr_every_n: number;
  plate_blur_enabled: boolean;
  buffer_queue_depth: number;
  last_heartbeat: string;
}

export interface ModelRegistryItem {
  file: string;
  purpose: string;
  status: string;
  license: string;
  sha256_prefix: string;
}

export interface PrivacyComplianceSummary {
  plate_mask_blur_kernel_px: number;
  retention_plain_hours: number;
  retention_flagged_days: number;
  plate_hash_algorithm: string;
  prohibited_attributes_detected: number;
  gnss_max_alignment_ms: number;
  imu_harsh_braking_threshold_mps2: number;
}

export interface FleetCompliancePayload {
  units: EdgeUnit[];
  models: ModelRegistryItem[];
  privacy: PrivacyComplianceSummary;
}

export interface PerceptionIngestRequest {
  label: string;
  confidence: number;
  frame_timestamp: string;
  bbox_area_ratio: number;
  model_version: string;
  gnss_samples: Array<{
    timestamp: string;
    latitude: number;
    longitude: number;
    accuracy_m: number;
    speed_kph: number;
    heading_deg?: number;
  }>;
  imu_sample?: {
    timestamp: string;
    longitudinal_accel_mps2: number;
    vertical_accel_mps2: number;
    yaw_rate_dps: number;
  };
  attributes?: Record<string, unknown>;
}

export interface PerceptionIngestResponse {
  event: RoadEventRecord;
  fusion: {
    age_ms: number;
    accuracy_m: number;
    speed_kph: number;
    road_segment_id: string | null;
    harsh_braking_detected: boolean;
  };
}

export const CATEGORY_META: Record<
  EventCategory,
  { label: string; shortLabel: string; color: string; bg: string }
> = {
  pothole: { label: 'Pothole', shortLabel: 'PH', color: '#EF4444', bg: 'rgba(239, 68, 68, 0.16)' },
  crack: { label: 'Surface Crack', shortLabel: 'CR', color: '#F97316', bg: 'rgba(249, 115, 22, 0.16)' },
  uneven_surface: { label: 'Uneven Surface', shortLabel: 'US', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.16)' },
  speed_breaker: { label: 'Speed Breaker', shortLabel: 'SB', color: '#FBBF24', bg: 'rgba(251, 191, 36, 0.16)' },
  obstacle: { label: 'Road Obstacle', shortLabel: 'OB', color: '#EC4899', bg: 'rgba(236, 72, 153, 0.16)' },
  waterlogging: { label: 'Waterlogging', shortLabel: 'WL', color: '#38BDF8', bg: 'rgba(56, 189, 248, 0.16)' },
  construction: { label: 'Construction', shortLabel: 'CN', color: '#FB923C', bg: 'rgba(251, 146, 60, 0.16)' },
  road_closure: { label: 'Road Closure', shortLabel: 'RC', color: '#DC2626', bg: 'rgba(220, 38, 38, 0.20)' },
  traffic_congestion: { label: 'Congestion', shortLabel: 'TC', color: '#A855F7', bg: 'rgba(168, 85, 247, 0.16)' },
  incident: { label: 'Incident', shortLabel: 'IN', color: '#F43F5E', bg: 'rgba(244, 63, 94, 0.16)' },
  speed_limit_sign: { label: 'Speed Sign', shortLabel: 'SL', color: '#22D3EE', bg: 'rgba(34, 211, 238, 0.16)' },
};

export const SOURCE_TYPE_META: Record<
  SourceType,
  { label: string; short: string; color: string; bg: string; isDirectObservation: boolean }
> = {
  camera_observed: {
    label: 'Camera Observed',
    short: 'Camera',
    color: '#10B981',
    bg: 'rgba(16, 185, 129, 0.16)',
    isDirectObservation: true,
  },
  sensor_observed: {
    label: 'IMU / Sensor Observed',
    short: 'IMU Sensor',
    color: '#22D3EE',
    bg: 'rgba(34, 211, 238, 0.16)',
    isDirectObservation: true,
  },
  telemetry_aggregated: {
    label: 'Telemetry Aggregated',
    short: 'Telemetry',
    color: '#60A5FA',
    bg: 'rgba(96, 165, 250, 0.16)',
    isDirectObservation: false,
  },
  external_provider: {
    label: 'External Provider',
    short: 'External',
    color: '#F59E0B',
    bg: 'rgba(245, 158, 11, 0.16)',
    isDirectObservation: false,
  },
  inferred: {
    label: 'Inferred Aggregate',
    short: 'Inferred',
    color: '#A78BFA',
    bg: 'rgba(167, 139, 250, 0.16)',
    isDirectObservation: false,
  },
};

export function formatUtcTime(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatRelativeAge(iso: string): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

