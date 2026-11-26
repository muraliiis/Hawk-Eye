import { useState, useCallback, useEffect } from 'react';
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  CircleMarker,
} from 'react-leaflet';
import L from 'leaflet';
import { Search, Navigation, MapPin, X } from 'lucide-react';
import { useMapStore } from '@/store/mapStore';
import { useRoadEvents } from '@/hooks/useRoadEvents';
import { useParkingAvailability } from '@/hooks/useParkingData';
import { useSSEStream } from '@/hooks/useSSE';
import { fetchRouteOptions } from '@/api/client';
import HazardAlertPanel from '@/components/HazardAlert';
import SpeedAdvisory from '@/components/SpeedAdvisory';
import RoutePanel from '@/components/RoutePanel';
import RoadConditionLayer from '@/components/RoadConditionLayer';
import { SeverityLevel, RouteScoringType } from '@/types';
import type { GPSCoord, RouteOption, TrafficSegment } from '@/types';
import { format } from 'date-fns';

// ─── Icon helpers (duplicated from NavigationMap for standalone page) ─────────

function severityColor(sev: SeverityLevel): string {
  switch (sev) {
    case SeverityLevel.CRITICAL: return '#ef4444';
    case SeverityLevel.HIGH:     return '#f97316';
    case SeverityLevel.MEDIUM:   return '#eab308';
    case SeverityLevel.LOW:      return '#22c55e';
    default:                     return '#6b7280';
  }
}

function makeEventIcon(sev: SeverityLevel) {
  const color = severityColor(sev);
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  });
}

const positionIcon = L.divIcon({
  className: 'position-pulse',
  html: `<div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;border:3px solid white;box-shadow:0 0 8px rgba(59,130,246,0.8);position:relative;"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

function occupancyColor(rate: number): string {
  if (rate < 0.5) return '#22c55e';
  if (rate < 0.8) return '#eab308';
  return '#ef4444';
}

// ─── Mock geocoder ────────────────────────────────────────────────────────────

function mockGeocode(query: string): GPSCoord | null {
  const known: Record<string, GPSCoord> = {
    'mumbai':     { lat: 19.0760, lon: 72.8777 },
    'delhi':      { lat: 28.6139, lon: 77.2090 },
    'bangalore':  { lat: 12.9716, lon: 77.5946 },
    'bengaluru':  { lat: 12.9716, lon: 77.5946 },
    'hyderabad':  { lat: 17.3850, lon: 78.4867 },
    'chennai':    { lat: 13.0827, lon: 80.2707 },
    'kolkata':    { lat: 22.5726, lon: 88.3639 },
    'pune':       { lat: 18.5204, lon: 73.8567 },
    'ahmedabad':  { lat: 23.0225, lon: 72.5714 },
    'jaipur':     { lat: 26.9124, lon: 75.7873 },
  };
  return known[query.toLowerCase().trim()] ?? null;
}

// ─── Mock road segments for condition layer demo ─────────────────────────────

const MOCK_SEGMENTS: TrafficSegment[] = [
  {
    id: 's1', name: 'NH-48 Section A',
    start: { lat: 28.60, lon: 77.20 }, end: { lat: 28.65, lon: 77.25 },
    quality_score: 8.2, pothole_density: 0.5, speed_limit_kmh: 80,
    current_speed_kmh: 72, congestion_level: 0.2,
  },
  {
    id: 's2', name: 'Ring Road Sector 9',
    start: { lat: 28.55, lon: 77.18 }, end: { lat: 28.58, lon: 77.22 },
    quality_score: 4.1, pothole_density: 3.2, speed_limit_kmh: 60,
    current_speed_kmh: 38, congestion_level: 0.6,
  },
  {
    id: 's3', name: 'Old NH-24 Bypass',
    start: { lat: 28.62, lon: 77.30 }, end: { lat: 28.65, lon: 77.35 },
    quality_score: 2.0, pothole_density: 7.8, speed_limit_kmh: 40,
    current_speed_kmh: 22, congestion_level: 0.8,
  },
];

// ─── Page Component ───────────────────────────────────────────────────────────

export default function NavigationPage() {
  const mapCenter           = useMapStore((s) => s.mapCenter);
  const mapZoom             = useMapStore((s) => s.mapZoom);
  const currentPosition     = useMapStore((s) => s.currentPosition);
  const roadEvents          = useMapStore((s) => s.roadEvents);
  const parkingObservations = useMapStore((s) => s.parkingObservations);
  const activeRoute         = useMapStore((s) => s.activeRoute);
  const setActiveRoute      = useMapStore((s) => s.setActiveRoute);
  const setMapView          = useMapStore((s) => s.setMapView);
  const setPosition         = useMapStore((s) => s.setPosition);

  const [destination, setDestination]       = useState('');
  const [destCoord, setDestCoord]           = useState<GPSCoord | null>(null);
  const [routes, setRoutes]                 = useState<RouteOption[]>([]);
  const [showParking, setShowParking]       = useState(false);
  const [isLoadingRoutes, setLoadingRoutes] = useState(false);
  const [searchError, setSearchError]       = useState('');

  // Real-time SSE stream
  useSSEStream();
  // Poll road events globally
  useRoadEvents();
  // Poll parking if enabled and position known
  const lat = currentPosition?.lat ?? null;
  const lon = currentPosition?.lon ?? null;
  useParkingAvailability(showParking ? lat : null, showParking ? lon : null, 1000);

  // Simulate GPS position on mount (India center for demo)
  useEffect(() => {
    setPosition({ lat: 20.5937, lon: 78.9629 });
  }, [setPosition]);

  const handleSearch = useCallback(async () => {
    setSearchError('');
    const coord = mockGeocode(destination);
    if (!coord) {
      setSearchError(`"${destination}" not found. Try: Mumbai, Delhi, Bangalore…`);
      return;
    }
    setDestCoord(coord);
    setMapView([coord.lat, coord.lon], 12);

    if (currentPosition) {
      setLoadingRoutes(true);
      try {
        const opts = await fetchRouteOptions(currentPosition, coord);
        setRoutes(opts);
        if (opts.length > 0) setActiveRoute(opts[0]);
      } catch {
        // Backend not reachable — generate mock routes for demo
        const mockRoutes: RouteOption[] = [
          {
            id: 'r1', scoring_type: RouteScoringType.FASTEST,
            polyline: [currentPosition, coord],
            distance_km: 12.4, estimated_time_min: 22,
            road_quality_score: 7.1, hazard_count: 2, congestion_level: 0.35,
          },
          {
            id: 'r2', scoring_type: RouteScoringType.SAFEST,
            polyline: [currentPosition, { lat: (currentPosition.lat + coord.lat) / 2 + 0.05, lon: (currentPosition.lon + coord.lon) / 2 }, coord],
            distance_km: 14.1, estimated_time_min: 28,
            road_quality_score: 9.0, hazard_count: 0, congestion_level: 0.15,
          },
          {
            id: 'r3', scoring_type: RouteScoringType.SMOOTHEST,
            polyline: [currentPosition, { lat: (currentPosition.lat + coord.lat) / 2, lon: (currentPosition.lon + coord.lon) / 2 - 0.05 }, coord],
            distance_km: 13.3, estimated_time_min: 25,
            road_quality_score: 8.6, hazard_count: 1, congestion_level: 0.2,
          },
          {
            id: 'r4', scoring_type: RouteScoringType.BALANCED,
            polyline: [currentPosition, coord],
            distance_km: 12.9, estimated_time_min: 24,
            road_quality_score: 8.0, hazard_count: 1, congestion_level: 0.25,
          },
        ];
        setRoutes(mockRoutes);
        setActiveRoute(mockRoutes[0]);
      } finally {
        setLoadingRoutes(false);
      }
    }
  }, [destination, currentPosition, setMapView, setActiveRoute]);

  return (
    <div className="relative w-full h-full overflow-hidden">
      {/* ── Full-screen Leaflet Map ───────────────────────────────────────── */}
      <MapContainer
        center={mapCenter}
        zoom={mapZoom}
        className="w-full h-full"
        zoomControl={true}
        style={{ zIndex: 0 }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Current position */}
        {currentPosition && (
          <Marker position={[currentPosition.lat, currentPosition.lon]} icon={positionIcon}>
            <Popup><div className="text-sm font-semibold">Your Location</div></Popup>
          </Marker>
        )}

        {/* Destination marker */}
        {destCoord && (
          <Marker
            position={[destCoord.lat, destCoord.lon]}
            icon={L.divIcon({
              className: '',
              html: `<div style="width:20px;height:20px;border-radius:50% 50% 50% 0;background:#a855f7;border:3px solid white;transform:rotate(-45deg);box-shadow:0 0 6px rgba(0,0,0,0.5)"></div>`,
              iconSize: [20, 20],
              iconAnchor: [10, 20],
            })}
          >
            <Popup><div className="text-sm font-semibold capitalize">{destination}</div></Popup>
          </Marker>
        )}

        {/* Road event markers */}
        {roadEvents.map((evt) => (
          <Marker
            key={evt.id}
            position={[evt.location?.lat ?? evt.lat ?? 0, evt.location?.lon ?? evt.lon ?? 0]}
            icon={makeEventIcon(evt.severity)}
          >
            <Popup>
              <div className="text-sm space-y-1 min-w-[180px]">
                <div className="font-semibold capitalize">
                  {evt.event_type.replace(/_/g, ' ')}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{ background: severityColor(evt.severity) + '30', color: severityColor(evt.severity) }}>
                    {evt.severity}
                  </span>
                  <span className="text-xs text-gray-500">{Math.round(evt.confidence * 100)}% conf.</span>
                </div>
                {evt.description && <div className="text-xs text-gray-600">{evt.description}</div>}
                <div className="text-xs text-gray-400">
                  {format(new Date(evt.reported_at ?? evt.observed_at ?? 0), 'dd MMM HH:mm')}
                </div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* Route polylines */}
        {routes.map((route) => {
          const isActive = activeRoute?.id === route.id;
          const positions = route.polyline.map((c) => [c.lat, c.lon] as [number, number]);
          return (
            <Polyline
              key={route.id}
              positions={positions}
              pathOptions={{
                color:     isActive ? '#3b82f6' : '#6b7280',
                weight:    isActive ? 5 : 3,
                opacity:   isActive ? 0.9 : 0.5,
                dashArray: isActive ? undefined : '6 4',
              }}
              eventHandlers={{ click: () => setActiveRoute(route) }}
            />
          );
        })}

        {/* Parking overlay */}
        {showParking && parkingObservations.map((obs) => {
          const color = occupancyColor(obs.occupancy_rate);
          return (
            <CircleMarker
              key={obs.id}
              center={[obs.location.lat, obs.location.lon]}
              radius={12}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.5, weight: 2 }}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold">{obs.segment_name ?? obs.segment_id}</div>
                  <div className="text-xs text-gray-500">
                    {Math.round(obs.occupancy_rate * 100)}% occupied
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}

        {/* Road condition polylines */}
        <RoadConditionLayer segments={MOCK_SEGMENTS} />
      </MapContainer>

      {/* ── Speed Advisory (top-center) ───────────────────────────────────── */}
      <SpeedAdvisory />

      {/* ── Route Panel (left side) ───────────────────────────────────────── */}
      {routes.length > 0 && (
        <div className="absolute top-20 left-4 z-[1000] w-72">
          <RoutePanel routes={routes} />
        </div>
      )}

      {/* ── Search Bar (top) ─────────────────────────────────────────────── */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] flex flex-col items-center gap-1">
        <div className="flex items-center bg-gray-900/95 backdrop-blur border border-gray-700 rounded-xl shadow-xl overflow-hidden">
          <MapPin className="w-4 h-4 text-gray-400 ml-3 shrink-0" />
          <input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search destination (e.g. Mumbai)"
            className="bg-transparent px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none w-64"
          />
          {destination && (
            <button
              onClick={() => { setDestination(''); setDestCoord(null); setRoutes([]); setSearchError(''); }}
              className="p-2 text-gray-500 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={handleSearch}
            disabled={!destination || isLoadingRoutes}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 transition-colors"
          >
            {isLoadingRoutes ? (
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {isLoadingRoutes ? 'Routing…' : 'Route'}
          </button>
        </div>
        {searchError && (
          <div className="bg-red-950 border border-red-700 text-red-300 text-xs px-3 py-1.5 rounded-lg">
            {searchError}
          </div>
        )}
      </div>

      {/* ── Bottom toolbar ────────────────────────────────────────────────── */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-2">
        {/* Parking toggle */}
        <button
          onClick={() => setShowParking((v) => !v)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border shadow transition-colors
            ${showParking ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-900/90 border-gray-700 text-gray-300 hover:bg-gray-800'}`}
        >
          P Parking
        </button>

        {/* Start Navigation */}
        {activeRoute && (
          <button
            onClick={() => {
              if (destCoord) setMapView([destCoord.lat, destCoord.lon], 14);
            }}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl shadow-lg transition-colors"
          >
            <Navigation className="w-4 h-4" />
            Start Navigation
          </button>
        )}
      </div>

      {/* ── Hazard Alerts (bottom-right) ─────────────────────────────────── */}
      <HazardAlertPanel />
    </div>
  );
}
