import { useEffect, useRef } from 'react';
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import { format } from 'date-fns';
import { useMapStore } from '@/store/mapStore';
import { useRoadEvents } from '@/hooks/useRoadEvents';
import { SeverityLevel } from '@/types';
import type { RouteOption } from '@/types';

// ─── Severity colour helpers ─────────────────────────────────────────────────

function severityColor(sev: SeverityLevel): string {
  switch (sev) {
    case SeverityLevel.CRITICAL: return '#ef4444';
    case SeverityLevel.HIGH:     return '#f97316';
    case SeverityLevel.MEDIUM:   return '#eab308';
    case SeverityLevel.LOW:      return '#22c55e';
    default:                     return '#6b7280';
  }
}

function makeEventIcon(sev: SeverityLevel): L.DivIcon {
  const color = severityColor(sev);
  return L.divIcon({
    className: '',
    html: `<div style="
      width:14px;height:14px;border-radius:50%;
      background:${color};border:2px solid white;
      box-shadow:0 0 4px rgba(0,0,0,0.5);
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  });
}

const positionIcon = L.divIcon({
  className: 'position-pulse',
  html: `<div style="
    width:16px;height:16px;border-radius:50%;
    background:#3b82f6;border:3px solid white;
    box-shadow:0 0 8px rgba(59,130,246,0.8);
    position:relative;
  "></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

// ─── Map view syncer ──────────────────────────────────────────────────────────

function MapViewSyncer() {
  const map = useMap();
  const mapCenter = useMapStore((s) => s.mapCenter);
  const mapZoom   = useMapStore((s) => s.mapZoom);
  const prevCenter = useRef<[number, number]>(mapCenter);
  const prevZoom   = useRef<number>(mapZoom);

  useEffect(() => {
    if (
      prevCenter.current[0] !== mapCenter[0] ||
      prevCenter.current[1] !== mapCenter[1] ||
      prevZoom.current !== mapZoom
    ) {
      map.setView(mapCenter, mapZoom);
      prevCenter.current = mapCenter;
      prevZoom.current   = mapZoom;
    }
  }, [map, mapCenter, mapZoom]);

  return null;
}

// ─── Route Polylines ─────────────────────────────────────────────────────────

interface RoutePolylinesProps {
  routes:      RouteOption[];
  activeRoute: RouteOption | null;
  onSelect:    (r: RouteOption) => void;
}

function RoutePolylines({ routes, activeRoute, onSelect }: RoutePolylinesProps) {
  return (
    <>
      {routes.map((route) => {
        const isActive = activeRoute?.id === route.id;
        const positions = route.polyline.map((c) => [c.lat, c.lon] as [number, number]);
        return (
          <Polyline
            key={route.id}
            positions={positions}
            pathOptions={{
              color:   isActive ? '#3b82f6' : '#6b7280',
              weight:  isActive ? 5 : 3,
              opacity: isActive ? 0.9 : 0.5,
              dashArray: isActive ? undefined : '6 4',
            }}
            eventHandlers={{ click: () => onSelect(route) }}
          />
        );
      })}
    </>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface NavigationMapProps {
  showParking?: boolean;
  showConditions?: boolean;
  className?: string;
}

export default function NavigationMap({
  className = '',
}: NavigationMapProps) {
  const mapCenter          = useMapStore((s) => s.mapCenter);
  const mapZoom            = useMapStore((s) => s.mapZoom);
  const currentPosition    = useMapStore((s) => s.currentPosition);
  const roadEvents         = useMapStore((s) => s.roadEvents);
  const activeRoute        = useMapStore((s) => s.activeRoute);
  const setActiveRoute     = useMapStore((s) => s.setActiveRoute);

  // The store already gets populated via this hook's onSuccess
  useRoadEvents();

  // Collect all route options from active + alternates stored in meta
  const allRoutes: RouteOption[] = activeRoute ? [activeRoute] : [];

  return (
    <div className={`relative w-full h-full ${className}`}>
      <MapContainer
        center={mapCenter}
        zoom={mapZoom}
        className="w-full h-full"
        zoomControl={true}
      >
        <MapViewSyncer />

        {/* Base tile layer */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Current position */}
        {currentPosition && (
          <Marker
            position={[currentPosition.lat, currentPosition.lon]}
            icon={positionIcon}
          >
            <Popup>
              <div className="text-sm font-semibold">Your Location</div>
              <div className="text-xs text-gray-500">
                {currentPosition.lat.toFixed(5)}, {currentPosition.lon.toFixed(5)}
              </div>
            </Popup>
          </Marker>
        )}

        {/* Road event markers */}
        {roadEvents.map((evt) => {
          const lat = evt.location?.lat ?? evt.lat;
          const lon = evt.location?.lon ?? evt.lon;
          if (lat === undefined || lon === undefined) return null;
          return (
            <Marker
              key={evt.id}
              position={[lat, lon]}
              icon={makeEventIcon(evt.severity)}
            >
              <Popup>
                <div className="text-sm space-y-1 min-w-[180px]">
                  <div className="font-semibold capitalize">
                    {evt.event_type.replace(/_/g, ' ')}
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-medium px-1.5 py-0.5 rounded"
                      style={{
                        background: severityColor(evt.severity) + '30',
                        color: severityColor(evt.severity),
                      }}
                    >
                      {evt.severity}
                    </span>
                    <span className="text-xs text-gray-500">
                      {Math.round(evt.confidence * 100)}% confidence
                    </span>
                  </div>
                  {evt.description && (
                    <div className="text-xs text-gray-600">{evt.description}</div>
                  )}
                  <div className="text-xs text-gray-400">
                    {format(new Date(evt.reported_at ?? evt.observed_at ?? Date.now()), 'dd MMM HH:mm')}
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* Route polylines */}
        <RoutePolylines
          routes={allRoutes}
          activeRoute={activeRoute}
          onSelect={setActiveRoute}
        />
      </MapContainer>
    </div>
  );
}

export { makeEventIcon, severityColor };
export type { NavigationMapProps };
