import { AlertTriangle, Cpu, EyeOff, Lock, Radio, ShieldCheck } from 'lucide-react';
import { formatRelativeAge, type FleetCompliancePayload, type ParkingSegment } from '@shared/types';

interface FleetSensorHealthProps {
  fleetData: FleetCompliancePayload | null;
  parking: ParkingSegment[];
}

export function FleetSensorHealth({ fleetData, parking }: FleetSensorHealthProps) {
  if (!fleetData) {
    return (
      <div className="scroll-view">
        <div className="panel-card">Loading edge fleet and compliance telemetry...</div>
      </div>
    );
  }

  return (
    <div className="scroll-view">
      <div className="panel-card">
        <div className="panel-header">
          <div className="panel-title">Edge Dashcam Fleet &amp; GNSS/IMU Sensor Fusion Health</div>
          <span className="badge" style={{ background: 'rgba(34,211,238,0.14)', color: 'var(--accent-cyan)' }}>
            Max GNSS Alignment Gate: {fleetData.privacy.gnss_max_alignment_ms} ms
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Unit ID</th>
                <th>Corridor</th>
                <th>Status</th>
                <th>GNSS Age</th>
                <th>Accuracy</th>
                <th>IMU Harsh Brakes (1h)</th>
                <th>FPS / Throttle</th>
                <th>Plate Blur</th>
                <th>Offline Buffer</th>
              </tr>
            </thead>
            <tbody>
              {fleetData.units.map((u) => {
                const stale = u.gnss_age_ms > u.gnss_max_alignment_ms;
                return (
                  <tr key={u.unit_id}>
                    <td>
                      <div className="mono" style={{ fontWeight: 700 }}>
                        {u.unit_id}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{u.vehicle_label}</div>
                    </td>
                    <td>{u.corridor}</td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          background:
                            u.status === 'online' ? 'rgba(16,185,129,0.16)' : 'rgba(239,68,68,0.16)',
                          color: u.status === 'online' ? 'var(--accent-emerald)' : 'var(--accent-red)',
                        }}
                      >
                        <Radio size={11} /> {u.status}
                      </span>
                    </td>
                    <td className="mono tabular" style={{ color: stale ? 'var(--accent-red)' : 'var(--accent-emerald)', fontWeight: 700 }}>
                      {u.gnss_age_ms} ms {stale ? '(STALE)' : ''}
                    </td>
                    <td className="tabular">±{u.gnss_accuracy_m}m</td>
                    <td className="tabular">{u.imu_harsh_brakes_1h}</td>
                    <td className="mono tabular" style={{ fontSize: 11 }}>
                      {u.fps} FPS · P/{u.parking_every_n} · ANPR/{u.anpr_every_n}
                    </td>
                    <td>
                      <span className="badge" style={{ background: 'rgba(16,185,129,0.16)', color: 'var(--accent-emerald)' }}>
                        <EyeOff size={11} /> {u.plate_blur_enabled ? 'ON' : 'OFF'}
                      </span>
                    </td>
                    <td className="tabular">{u.buffer_queue_depth} queued</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <div className="panel-card">
          <div className="panel-header">
            <div className="panel-title">
              <Cpu size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Model Registry (models/manifest.json)
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {fleetData.models.map((m) => {
              const isPending = m.status === 'training_pending';
              return (
                <div
                  key={m.file}
                  style={{
                    padding: 10,
                    borderRadius: 10,
                    background: 'var(--bg-elevated)',
                    border: `1px solid ${isPending ? 'rgba(245,158,11,0.4)' : 'var(--border-subtle)'}`,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <span className="mono" style={{ fontWeight: 700, fontSize: 12.5 }}>
                      {m.file}
                    </span>
                    <span
                      className="badge"
                      style={{
                        background: isPending ? 'rgba(245,158,11,0.16)' : 'rgba(16,185,129,0.16)',
                        color: isPending ? 'var(--accent-amber)' : 'var(--accent-emerald)',
                      }}
                    >
                      {m.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{m.purpose}</div>
                  <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-muted)', marginTop: 4 }}>
                    sha256:{m.sha256_prefix} · {m.license}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="panel-card">
          <div className="panel-header">
            <div className="panel-title">
              <Lock size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Parking &amp; ANPR Privacy Compliance Vault
            </div>
            <span className="badge" style={{ background: 'rgba(16,185,129,0.16)', color: 'var(--accent-emerald)' }}>
              <ShieldCheck size={12} /> {fleetData.privacy.prohibited_attributes_detected} PII Violations
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14, fontSize: 12 }}>
            <div style={{ padding: 10, borderRadius: 8, background: 'var(--bg-elevated)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>Standard Retention</div>
              <strong className="tabular">{fleetData.privacy.retention_plain_hours} hours</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'var(--bg-elevated)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>Flagged Retention</div>
              <strong className="tabular">{fleetData.privacy.retention_flagged_days} days</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'var(--bg-elevated)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>Frame Blur Kernel</div>
              <strong className="tabular">{fleetData.privacy.plate_mask_blur_kernel_px}×{fleetData.privacy.plate_mask_blur_kernel_px} px</strong>
            </div>
            <div style={{ padding: 10, borderRadius: 8, background: 'var(--bg-elevated)' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>Storage Digest</div>
              <strong style={{ fontSize: 11.5 }}>{fleetData.privacy.plate_hash_algorithm}</strong>
            </div>
          </div>

          <div className="panel-title" style={{ marginBottom: 6 }}>
            Roadside Parking Occupancy Corridors (Anonymized)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {parking.map((p) => (
              <div
                key={p.road_segment_id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 12,
                  padding: '6px 8px',
                  borderRadius: 8,
                  background: 'var(--bg-elevated)',
                }}
              >
                <span>{p.segment_name}</span>
                <span className="tabular">
                  <strong>{p.available_spaces}</strong>/{p.total_spaces_estimated} open · {formatRelativeAge(p.last_observed)}
                </span>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, fontSize: 11.5, color: 'var(--text-secondary)' }}>
            <AlertTriangle size={13} color="var(--accent-amber)" />
            Plate text and raw imagery are strictly isolated from the RoadEvent stream.
          </div>
        </div>
      </div>
    </div>
  );
}

