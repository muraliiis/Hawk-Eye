import { EyeOff, Lock, ShieldCheck, Volume2 } from 'lucide-react';

interface SafetyPrivacyPanelProps {
  dashcamOptIn: boolean;
  onToggleDashcamOptIn: () => void;
  telemetryOptIn: boolean;
  onToggleTelemetryOptIn: () => void;
  audioChimesEnabled: boolean;
  onToggleAudioChimes: () => void;
}

export function SafetyPrivacyPanel({
  dashcamOptIn,
  onToggleDashcamOptIn,
  telemetryOptIn,
  onToggleTelemetryOptIn,
  audioChimesEnabled,
  onToggleAudioChimes,
}: SafetyPrivacyPanelProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-title">
          <span>Driver Consent &amp; Privacy Controls</span>
          <span className="badge" style={{ background: 'rgba(16,185,129,0.16)', color: '#6EE7B7' }}>
            Contract v1 Enforced
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>Dashcam Hazard Upload</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                Publish normalized defects via SensorFusion &amp; PerceptionNormalizer
              </div>
            </div>
            <input type="checkbox" checked={dashcamOptIn} onChange={onToggleDashcamOptIn} />
          </label>

          <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>Anonymous Segment Speed Telemetry</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                Contribute aggregated speed samples without vehicle identifiers
              </div>
            </div>
            <input type="checkbox" checked={telemetryOptIn} onChange={onToggleTelemetryOptIn} />
          </label>

          <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, cursor: 'pointer' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>
                <Volume2 size={13} style={{ verticalAlign: 'middle', marginRight: 5 }} />
                Hazard Proximity Audio Chime
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
                Subtle tone when approaching a hazard within 80 m
              </div>
            </div>
            <input type="checkbox" checked={audioChimesEnabled} onChange={onToggleAudioChimes} />
          </label>
        </div>
      </div>

      <div className="card" style={{ borderColor: 'rgba(34,211,238,0.35)' }}>
        <div className="card-title">
          <span>Mandatory Guardrails (Locked)</span>
          <Lock size={13} color="#22D3EE" />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9, fontSize: 12, color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <EyeOff size={16} color="#10B981" style={{ flexShrink: 0 }} />
            <span>
              <strong>On-Device Plate Blurring:</strong> Always enabled (51px Gaussian kernel). Raw imagery and plate
              text are prohibited from <span className="mono">RoadEvent.attributes</span>.
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <ShieldCheck size={16} color="#22D3EE" style={{ flexShrink: 0 }} />
            <span>
              <strong>Legal vs. Advisory Separation:</strong> Legal speed limits remain regulatory; hazard slowdowns
              within 80 m are strictly marked non-legal advisories.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

