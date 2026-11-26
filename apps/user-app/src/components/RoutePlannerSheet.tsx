import { ArrowLeftRight, Navigation, ShieldCheck, Sparkles, Zap, Compass } from 'lucide-react';
import {
  CATEGORY_META,
  SOURCE_TYPE_META,
  type GraphNode,
  type RoadEventRecord,
  type RouteComparisonItem,
  type RouteProfile,
} from '@shared/types';

interface RoutePlannerSheetProps {
  nodes: GraphNode[];
  origin: string;
  destination: string;
  onChangeOrigin: (id: string) => void;
  onChangeDestination: (id: string) => void;
  onSwap: () => void;
  routes: RouteComparisonItem[];
  selectedProfile: RouteProfile;
  onSelectProfile: (profile: RouteProfile) => void;
  onStartNavigation: () => void;
  selectedEvent: RoadEventRecord | null;
  onClearSelectedEvent: () => void;
  onFeedback: (eventId: string, action: 'confirm' | 'cleared') => Promise<void>;
  loadingRoutes: boolean;
  routeGeometryWarning: boolean;
}

const PROFILE_ICON: Record<RouteProfile, typeof ShieldCheck> = {
  balanced: Compass,
  safest: ShieldCheck,
  smoothest: Sparkles,
  fastest: Zap,
};

const PROFILE_TITLE: Record<RouteProfile, string> = {
  balanced: 'Balanced',
  safest: 'Safest',
  smoothest: 'Smoothest',
  fastest: 'Fastest',
};

export function RoutePlannerSheet({
  nodes,
  origin,
  destination,
  onChangeOrigin,
  onChangeDestination,
  onSwap,
  routes,
  selectedProfile,
  onSelectProfile,
  onStartNavigation,
  selectedEvent,
  onClearSelectedEvent,
  onFeedback,
  loadingRoutes,
  routeGeometryWarning,
}: RoutePlannerSheetProps) {
  const activeRoute = routes.find((r) => r.profile === selectedProfile);
  const canNavigate = Boolean(activeRoute);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div className="card">
        <div className="card-title">
          <span>Route Planner · Bengaluru</span>
          <span className="badge" style={{ background: 'rgba(34,211,238,0.14)', color: 'var(--accent-cyan)' }}>
            Multi-Objective Router
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              Origin
            </label>
            <select
              aria-label="Origin"
              className="select-field"
              value={origin}
              onChange={(e) => onChangeOrigin(e.target.value)}
            >
              {nodes.map((n) => (
                <option key={n.id} value={n.id} disabled={n.id === destination}>
                  {n.name} ({n.area})
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button type="button" className="pill-btn" onClick={onSwap} title="Swap origin and destination">
              <ArrowLeftRight size={13} /> Swap
            </button>
          </div>

          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
              Destination
            </label>
            <select
              aria-label="Destination"
              className="select-field"
              value={destination}
              onChange={(e) => onChangeDestination(e.target.value)}
            >
              {nodes.map((n) => (
                <option key={n.id} value={n.id} disabled={n.id === origin}>
                  {n.name} ({n.area})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="card-title" style={{ marginBottom: 2 }}>
          <span>Compare Routing Profiles</span>
          {loadingRoutes && <span style={{ color: 'var(--accent-cyan)' }}>Recalculating...</span>}
          {!loadingRoutes && routeGeometryWarning && (
            <span style={{ color: 'var(--accent-amber)' }}>Offline fallback corridor</span>
          )}
          {!loadingRoutes && !routeGeometryWarning && routes.length > 0 && (
            <span style={{ color: 'var(--accent-emerald)' }}>Road-constrained</span>
          )}
        </div>

        {routes.map((route) => {
          const Icon = PROFILE_ICON[route.profile];
          const isSelected = route.profile === selectedProfile;
          const qualityColor =
            route.road_quality_score >= 80
              ? 'var(--accent-emerald)'
              : route.road_quality_score >= 60
                ? 'var(--accent-amber)'
                : 'var(--accent-red)';

          return (
            <button
              key={route.profile}
              type="button"
              className={`route-card ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelectProfile(route.profile)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, fontSize: 14 }}>
                  <Icon size={16} color={isSelected ? '#22D3EE' : '#94A3B8'} />
                  <span>{PROFILE_TITLE[route.profile]}</span>
                </div>
                <div className="tabular" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 800, fontSize: 15 }}>{route.travel_minutes} min</span>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{route.distance_km} km</span>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span
                  className="badge tabular"
                  style={{ background: 'rgba(15,23,42,0.85)', color: qualityColor, border: '1px solid var(--border-subtle)' }}
                >
                  Quality {route.road_quality_score}/100
                </span>
                <span
                  className="badge tabular"
                  style={{
                    background: route.hazard_count > 3 ? 'rgba(239,68,68,0.16)' : 'rgba(16,185,129,0.15)',
                    color: route.hazard_count > 3 ? '#FCA5A5' : '#6EE7B7',
                  }}
                >
                  {route.hazard_count} {route.hazard_count === 1 ? 'hazard' : 'hazards'}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  via {route.node_names.slice(1, -1).join(' → ') || 'Direct'}
                </span>
              </div>

              <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.35 }}>
                {route.explanation}
              </div>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="btn-primary"
        disabled={!canNavigate}
        onClick={onStartNavigation}
        title={canNavigate ? 'Start road-constrained navigation' : 'Waiting for road-network geometry'}
      >
        <Navigation size={17} />
        {activeRoute
          ? `Start Safe Navigation (${PROFILE_TITLE[activeRoute.profile]})`
          : 'Waiting for road geometry'}
      </button>

      {selectedEvent && (
        <div className="card" style={{ borderColor: CATEGORY_META[selectedEvent.category].color }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span
              className="badge"
              style={{
                background: CATEGORY_META[selectedEvent.category].bg,
                color: CATEGORY_META[selectedEvent.category].color,
              }}
            >
              {CATEGORY_META[selectedEvent.category].label}
            </span>
            <button type="button" className="pill-btn" onClick={onClearSelectedEvent} style={{ padding: '3px 8px' }}>
              Close
            </button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            <span
              className="badge"
              style={{
                background: SOURCE_TYPE_META[selectedEvent.source_type].bg,
                color: SOURCE_TYPE_META[selectedEvent.source_type].color,
              }}
            >
              {SOURCE_TYPE_META[selectedEvent.source_type].label}
            </span>
            <span className="badge tabular" style={{ background: '#0b1220', color: 'var(--text-secondary)' }}>
              {Math.round(selectedEvent.confidence * 100)}% conf · ±{selectedEvent.location_accuracy_m}m
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10 }}>
            Segment: <span className="mono">{selectedEvent.road_segment_id || 'Unassigned'}</span> ·{' '}
            Confirmations: {selectedEvent.confirmations}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="btn-secondary"
              style={{ flex: 1 }}
              onClick={() => onFeedback(selectedEvent.event_id, 'confirm')}
            >
              Still There
            </button>
            <button
              type="button"
              className="btn-secondary"
              style={{ flex: 1 }}
              onClick={() => onFeedback(selectedEvent.event_id, 'cleared')}
            >
              Cleared
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

