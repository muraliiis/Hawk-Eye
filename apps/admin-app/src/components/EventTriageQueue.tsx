import { useMemo, useState } from 'react';
import { CheckCircle2, Eye, Search, XCircle } from 'lucide-react';
import {
  CATEGORY_META,
  SOURCE_TYPE_META,
  formatUtcTime,
  type RoadEventRecord,
  type WorkflowStatus,
} from '@shared/types';

interface EventTriageQueueProps {
  events: RoadEventRecord[];
  onInspect: (event: RoadEventRecord) => void;
  onModerateEvent: (eventId: string, status: WorkflowStatus) => Promise<void>;
}

export function EventTriageQueue({
  events,
  onInspect,
  onModerateEvent,
}: EventTriageQueueProps) {
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [minConfidence, setMinConfidence] = useState(0.45);
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (categoryFilter !== 'all' && e.category !== categoryFilter) return false;
      if (sourceFilter !== 'all' && e.source_type !== sourceFilter) return false;
      if (statusFilter !== 'all' && e.workflow_status !== statusFilter) return false;
      if (e.confidence < minConfidence) return false;
      if (query.trim()) {
        const q = query.trim().toLowerCase();
        const hay = `${e.event_id} ${e.category} ${e.road_segment_id || ''} ${e.source_type}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [events, categoryFilter, sourceFilter, statusFilter, minConfidence, query]);

  return (
    <div className="scroll-view">
      <div className="panel-card">
        <div className="panel-header">
          <div>
            <div className="panel-title">Event Triage &amp; Provenance Verification Queue</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Source provenance separates direct <span className="mono">camera_observed</span> sightings from{' '}
              <span className="mono">inferred</span> / <span className="mono">external_provider</span> signals.
            </div>
          </div>
          <span className="badge tabular" style={{ background: 'var(--bg-elevated)', color: 'var(--accent-cyan)' }}>
            Showing {filtered.length} of {events.length} events
          </span>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: '1 1 200px' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: 10, top: 10, color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              className="input-control"
              placeholder="Search event_id or segment..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ width: '100%', paddingLeft: 30 }}
            />
          </div>

          <select
            className="input-control"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">All Categories</option>
            {Object.entries(CATEGORY_META).map(([k, meta]) => (
              <option key={k} value={k}>
                {meta.label}
              </option>
            ))}
          </select>

          <select
            className="input-control"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="all">All Provenance Sources</option>
            {Object.entries(SOURCE_TYPE_META).map(([k, meta]) => (
              <option key={k} value={k}>
                {meta.label}
              </option>
            ))}
          </select>

          <select
            className="input-control"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="verified">Verified</option>
            <option value="resolved">Resolved</option>
            <option value="dismissed">Dismissed</option>
          </select>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
            <span>Min Conf:</span>
            <input
              type="range"
              min={0.45}
              max={0.95}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            />
            <strong className="mono tabular">{Math.round(minConfidence * 100)}%</strong>
          </label>
        </div>
      </div>

      <div className="panel-card" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Provenance (source_type)</th>
              <th>Road Segment</th>
              <th>Confidence</th>
              <th>Accuracy</th>
              <th>Status</th>
              <th>Observed UTC</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((evt) => {
              const cat = CATEGORY_META[evt.category];
              const src = SOURCE_TYPE_META[evt.source_type];
              return (
                <tr key={evt.event_id}>
                  <td>
                    <span className="badge" style={{ background: cat.bg, color: cat.color }}>
                      {cat.label}
                    </span>
                  </td>
                  <td>
                    <span className="badge" style={{ background: src.bg, color: src.color }}>
                      {src.label}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 11.5 }}>
                    {evt.road_segment_id || 'Unmapped'}
                  </td>
                  <td className="tabular">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 52, height: 6, borderRadius: 999, background: 'var(--bg-elevated)', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${Math.round(evt.confidence * 100)}%`,
                            height: '100%',
                            background: evt.confidence >= 0.8 ? 'var(--accent-emerald)' : 'var(--accent-amber)',
                          }}
                        />
                      </div>
                      <strong>{Math.round(evt.confidence * 100)}%</strong>
                    </div>
                  </td>
                  <td className="tabular">±{evt.location_accuracy_m}m</td>
                  <td>
                    <span className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
                      {evt.workflow_status}
                    </span>
                  </td>
                  <td className="mono tabular" style={{ fontSize: 11.5 }}>
                    {formatUtcTime(evt.observed_at)}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button type="button" className="btn" onClick={() => onInspect(evt)} title="Inspect on map">
                        <Eye size={13} />
                      </button>
                      <button
                        type="button"
                        className="btn success"
                        onClick={() => onModerateEvent(evt.event_id, 'verified')}
                        title="Verify hazard"
                      >
                        <CheckCircle2 size={13} />
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => onModerateEvent(evt.event_id, 'resolved')}
                        title="Mark resolved"
                      >
                        Resolve
                      </button>
                      <button
                        type="button"
                        className="btn danger"
                        onClick={() => onModerateEvent(evt.event_id, 'dismissed')}
                        title="Dismiss"
                      >
                        <XCircle size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

