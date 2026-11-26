import { useState } from 'react';
import { Polyline, Popup } from 'react-leaflet';
import { Layers, LayersIcon } from 'lucide-react';
import type { TrafficSegment } from '@/types';

function qualityColor(score: number): string {
  // Interpolate: 0=red, 5=yellow, 10=green
  if (score >= 7) return '#22c55e';
  if (score >= 4) return '#eab308';
  return '#ef4444';
}

function qualityWeight(score: number): number {
  return 3 + (1 - score / 10) * 3; // thicker lines = worse roads
}

interface RoadConditionLayerProps {
  segments: TrafficSegment[];
}

export default function RoadConditionLayer({ segments }: RoadConditionLayerProps) {
  const [visible, setVisible] = useState(false);

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setVisible((v) => !v)}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
          border transition-colors shadow
          ${visible
            ? 'bg-green-700 border-green-600 text-white'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'}
        `}
        title="Toggle road conditions"
      >
        {visible ? <Layers className="w-3.5 h-3.5" /> : <LayersIcon className="w-3.5 h-3.5" />}
        Road Conditions
      </button>

      {/* Polylines — rendered inside MapContainer context */}
      {visible &&
        segments.map((seg) => {
          const color  = qualityColor(seg.quality_score);
          const weight = qualityWeight(seg.quality_score);

          return (
            <Polyline
              key={seg.id}
              positions={[
                [seg.start.lat, seg.start.lon],
                [seg.end.lat,   seg.end.lon],
              ]}
              pathOptions={{ color, weight, opacity: 0.8 }}
            >
              <Popup>
                <div className="text-sm space-y-1 min-w-[180px]">
                  <div className="font-semibold">{seg.name}</div>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-medium px-1.5 py-0.5 rounded"
                      style={{ background: color + '30', color }}
                    >
                      Quality {seg.quality_score.toFixed(1)} / 10
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    Potholes: {seg.pothole_density.toFixed(1)} / km
                  </div>
                  {seg.speed_limit_kmh != null && (
                    <div className="text-xs text-gray-500">
                      Speed limit: {seg.speed_limit_kmh} km/h
                    </div>
                  )}
                  {seg.current_speed_kmh != null && (
                    <div className="text-xs text-gray-500">
                      Current speed: {seg.current_speed_kmh} km/h
                    </div>
                  )}
                </div>
              </Popup>
            </Polyline>
          );
        })}
    </>
  );
}
