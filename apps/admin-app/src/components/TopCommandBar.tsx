import { Activity, AlertTriangle, Moon, Radio, ShieldCheck, Sun, Zap } from 'lucide-react';

interface TopCommandBarProps {
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  streamConnected: boolean;
  activeHazardCount: number;
  congestedSegmentCount: number;
  onlineFleetCount: number;
  totalFleetCount: number;
  piiViolations: number;
  simulating: boolean;
  onSimulateBurst: () => void;
}

export function TopCommandBar({
  theme,
  onToggleTheme,
  streamConnected,
  activeHazardCount,
  congestedSegmentCount,
  onlineFleetCount,
  totalFleetCount,
  piiViolations,
  simulating,
  onSimulateBurst,
}: TopCommandBarProps) {
  return (
    <header className="command-bar">
      <div className="brand-group">
        <div className="brand-icon">
          <Radio size={18} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 15, letterSpacing: '-0.02em' }}>
            RoadSense Control Room
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
            City Road Health · Event Triage · Fleet &amp; Privacy Governance
          </div>
        </div>
      </div>

      <div className="kpi-strip">
        <div className="kpi-pill tabular">
          <AlertTriangle size={13} color="var(--accent-amber)" />
          <span>Active Hazards:</span>
          <strong>{activeHazardCount}</strong>
        </div>

        <div className="kpi-pill tabular">
          <Activity size={13} color="var(--accent-violet)" />
          <span>Congested Links:</span>
          <strong>{congestedSegmentCount}</strong>
        </div>

        <div className="kpi-pill tabular">
          <Radio size={13} color="var(--accent-cyan)" />
          <span>Edge Fleet:</span>
          <strong>
            {onlineFleetCount}/{totalFleetCount} online
          </strong>
        </div>

        <div className="kpi-pill tabular">
          <ShieldCheck size={13} color="var(--accent-emerald)" />
          <span>PII Guardrail:</span>
          <strong style={{ color: piiViolations === 0 ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
            {piiViolations} leaks
          </strong>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="kpi-pill" title="Backend SSE event stream">
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: streamConnected ? 'var(--accent-emerald)' : 'var(--accent-amber)',
            }}
          />
          {streamConnected ? 'SSE Live' : 'Reconnecting'}
        </span>

        <button type="button" className="btn primary" disabled={simulating} onClick={onSimulateBurst}>
          <Zap size={14} /> {simulating ? 'Injecting...' : 'Simulate Detection'}
        </button>

        <button
          type="button"
          className="btn"
          onClick={onToggleTheme}
          title="Toggle Control Room Dark / Light theme"
        >
          {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        </button>
      </div>
    </header>
  );
}

