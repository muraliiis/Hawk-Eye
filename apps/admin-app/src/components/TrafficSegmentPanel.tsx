import { useState } from 'react';
import { Activity, Ban, CheckCircle2, Gauge } from 'lucide-react';
import type { RoadSegment } from '@shared/types';

interface TrafficSegmentPanelProps {
  segments: RoadSegment[];
  onToggleClosed: (segmentId: string, closed: boolean) => Promise<void>;
  onInjectTraffic: (segmentId: string, meanSpeedKph: number, vehicleCount: number) => Promise<void>;
}

export function TrafficSegmentPanel({
  segments,
  onToggleClosed,
  onInjectTraffic,
}: TrafficSegmentPanelProps) {
  const [speedInputs, setSpeedInputs] = useState<Record<string, number>>({});

  return (
    <div className="scroll-view">
      <div className="panel-card">
        <div className="panel-header">
          <div>
            <div className="panel-title">Segment Traffic Intelligence &amp; Routing Overrides</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Congestion threshold is <span className="mono">congestion_ratio &gt;= 0.45</span> in{' '}
              <span className="mono">TrafficIntelligence</span>. Closing a road immediately triggers User App rerouting.
            </div>
          </div>
        </div>
      </div>

      <div className="panel-card" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Corridor / Segment</th>
              <th>Legal Limit</th>
              <th>Mean vs Free-Flow</th>
              <th>Congestion Ratio</th>
              <th>Routing Penalties (Qual / Haz)</th>
              <th>Telemetry Injection</th>
              <th>Road State</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((seg) => {
              const pct = Math.round(seg.traffic.congestion_ratio * 100);
              const draftSpeed = speedInputs[seg.segment_id] ?? Math.round(seg.traffic.mean_speed_kph);
              return (
                <tr key={seg.segment_id}>
                  <td>
                    <div style={{ fontWeight: 700 }}>{seg.name}</div>
                    <div className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                      {seg.segment_id} · {seg.distance_km} km
                    </div>
                  </td>
                  <td className="tabular">
                    <span className="badge" style={{ background: 'var(--bg-elevated)' }}>
                      {seg.legal_speed_limit_kph} km/h
                    </span>
                  </td>
                  <td className="tabular">
                    <strong>{seg.traffic.mean_speed_kph}</strong> / {seg.traffic.free_flow_speed_kph} km/h
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                      {seg.traffic.vehicle_count} vehicles sampled
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div
                        style={{
                          position: 'relative',
                          width: 90,
                          height: 8,
                          borderRadius: 999,
                          background: 'var(--bg-elevated)',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            width: `${pct}%`,
                            height: '100%',
                            background: seg.traffic.is_congested ? 'var(--accent-violet)' : 'var(--accent-emerald)',
                          }}
                        />
                      </div>
                      <span
                        className="badge tabular"
                        style={{
                          background: seg.traffic.is_congested
                            ? 'rgba(167, 139, 250, 0.18)'
                            : 'rgba(16, 185, 129, 0.14)',
                          color: seg.traffic.is_congested ? 'var(--accent-violet)' : 'var(--accent-emerald)',
                        }}
                      >
                        {pct}% {seg.traffic.is_congested ? 'CONGESTED' : 'FLOW'}
                      </span>
                    </div>
                  </td>
                  <td className="mono tabular" style={{ fontSize: 11.5 }}>
                    Q: {seg.road_quality_penalty} · H: {seg.hazard_penalty}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <input
                        type="number"
                        min={5}
                        max={80}
                        value={draftSpeed}
                        onChange={(e) =>
                          setSpeedInputs((prev) => ({
                            ...prev,
                            [seg.segment_id]: Number(e.target.value) || 15,
                          }))
                        }
                        className="input-control tabular"
                        style={{ width: 64, padding: '5px 7px' }}
                        aria-label={`Mean speed for ${seg.name}`}
                      />
                      <button
                        type="button"
                        className="btn"
                        onClick={() => onInjectTraffic(seg.segment_id, draftSpeed, 18)}
                        title="Feed observation into TrafficIntelligence"
                      >
                        <Gauge size={13} /> Sample
                      </button>
                    </div>
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`btn ${seg.closed ? 'success' : 'danger'}`}
                      onClick={() => onToggleClosed(seg.segment_id, !seg.closed)}
                    >
                      {seg.closed ? (
                        <>
                          <CheckCircle2 size={13} /> Reopen Road
                        </>
                      ) : (
                        <>
                          <Ban size={13} /> Close Road
                        </>
                      )}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="panel-card" style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}>
        <Activity size={16} color="var(--accent-cyan)" />
        <span>
          All congestion alerts emitted from this table carry <span className="mono">source_type="inferred"</span> per{' '}
          <span className="mono">docs/architecture.md</span>.
        </span>
      </div>
    </div>
  );
}

