import { useState } from 'react';
import { CircleMarker, Popup } from 'react-leaflet';
import { ParkingSquare, Eye, EyeOff } from 'lucide-react';
import { format } from 'date-fns';
import { useMapStore } from '@/store/mapStore';
import { useParkingAvailability } from '@/hooks/useParkingData';

function occupancyColor(rate: number): string {
  if (rate < 0.5) return '#22c55e'; // green
  if (rate < 0.8) return '#eab308'; // yellow
  return '#ef4444';                  // red
}

function occupancyLabel(rate: number): string {
  if (rate < 0.5) return 'Available';
  if (rate < 0.8) return 'Moderate';
  return 'Full';
}

export default function ParkingOverlay() {
  const [visible, setVisible] = useState(false);
  const currentPosition    = useMapStore((s) => s.currentPosition);
  const parkingObservations = useMapStore((s) => s.parkingObservations);

  const lat = currentPosition?.lat ?? null;
  const lon = currentPosition?.lon ?? null;

  const { isLoading } = useParkingAvailability(lat, lon, 1000);

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setVisible((v) => !v)}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
          border transition-colors shadow
          ${visible
            ? 'bg-blue-600 border-blue-500 text-white'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'}
        `}
        disabled={isLoading}
        title="Toggle parking overlay"
      >
        {visible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
        <ParkingSquare className="w-3.5 h-3.5" />
        Parking
        {isLoading && <span className="ml-1 animate-pulse">…</span>}
      </button>

      {/* Leaflet markers — only rendered inside a MapContainer context */}
      {visible && parkingObservations.map((obs) => {
        const color = occupancyColor(obs.occupancy_rate);
        const radius = 10 + obs.occupancy_rate * 8;
        return (
          <CircleMarker
            key={obs.id}
            center={[obs.location.lat, obs.location.lon]}
            radius={radius}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.5,
              weight: 2,
            }}
          >
            <Popup>
              <div className="text-sm space-y-1 min-w-[180px]">
                <div className="font-semibold">
                  {obs.segment_name ?? obs.segment_id}
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className="text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{ background: color + '30', color }}
                  >
                    {occupancyLabel(obs.occupancy_rate)}
                  </span>
                  <span className="text-xs text-gray-500">
                    {Math.round(obs.occupancy_rate * 100)}% occupied
                  </span>
                </div>
                {obs.total_spaces != null && (
                  <div className="text-xs text-gray-500">
                    {obs.occupied_spaces ?? '?'} / {obs.total_spaces} spaces
                  </div>
                )}
                <div className="text-xs text-gray-400">
                  Updated {format(new Date(obs.observed_at), 'HH:mm')}
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}
