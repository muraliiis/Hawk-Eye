import { Car, Clock, Navigation, Shield } from 'lucide-react';
import { formatRelativeAge, type ParkingSegment } from '@shared/types';

interface ParkingFinderDrawerProps {
  parking: ParkingSegment[];
  onNavigateToParking: (segmentId: string) => void;
}

export function ParkingFinderDrawer({ parking, onNavigateToParking }: ParkingFinderDrawerProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-title">
          <span>Roadside Parking Availability</span>
          <span className="badge" style={{ background: 'rgba(16,185,129,0.16)', color: '#6EE7B7' }}>
            <Shield size={11} /> Privacy-Masked
          </span>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
          Estimated from sliding-window roadside occupancy (<span className="mono">OccupancyEstimator</span>). License
          plates are blurred on-device and never exposed in driver feeds.
        </div>
      </div>

      {parking.map((bay) => {
        const occPct = Math.round(bay.occupancy_rate * 100);
        const availColor =
          bay.available_spaces >= 6 ? '#10B981' : bay.available_spaces >= 3 ? '#F59E0B' : '#EF4444';

        return (
          <div key={bay.road_segment_id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{bay.segment_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{bay.area}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div className="tabular" style={{ fontSize: 20, fontWeight: 800, color: availColor, lineHeight: 1 }}>
                  {bay.available_spaces}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                  of {bay.total_spaces_estimated} open
                </div>
              </div>
            </div>

            <div style={{ height: 6, borderRadius: 999, background: '#090F1A', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${occPct}%`,
                  height: '100%',
                  background: availColor,
                }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11.5, color: 'var(--text-secondary)' }}>
              <span className="tabular">
                <Car size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                {occPct}% occupied · {Math.round(bay.confidence * 100)}% conf
              </span>
              <span>
                <Clock size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                {formatRelativeAge(bay.last_observed)}
              </span>
            </div>

            <button
              type="button"
              className="btn-secondary"
              onClick={() => onNavigateToParking(bay.road_segment_id)}
            >
              <Navigation size={13} /> Plan Safe Route Nearby
            </button>
          </div>
        );
      })}
    </div>
  );
}

