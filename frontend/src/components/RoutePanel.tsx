import clsx from 'clsx';
import {
  Clock,
  Route,
  ShieldCheck,
  Sparkles,
  Scale,
  Navigation,
  AlertTriangle,
  Gauge,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useMapStore } from '@/store/mapStore';
import { RouteScoringType } from '@/types';
import type { RouteOption } from '@/types';
import { useState } from 'react';

function congestionLabel(level: number) {
  if (level < 0.3) return { label: 'Free flow', color: 'text-green-400' };
  if (level < 0.6) return { label: 'Moderate',  color: 'text-yellow-400' };
  if (level < 0.8) return { label: 'Heavy',     color: 'text-orange-400' };
  return                   { label: 'Gridlock', color: 'text-red-400' };
}

function qualityBar(score: number) {
  const pct = (score / 10) * 100;
  const color = score >= 7 ? 'bg-green-500' : score >= 4 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-6 text-right">{score.toFixed(1)}</span>
    </div>
  );
}

function scoringIcon(type: RouteScoringType) {
  switch (type) {
    case RouteScoringType.FASTEST:   return <Clock className="w-4 h-4 text-blue-400" />;
    case RouteScoringType.SAFEST:    return <ShieldCheck className="w-4 h-4 text-green-400" />;
    case RouteScoringType.SMOOTHEST: return <Sparkles className="w-4 h-4 text-purple-400" />;
    case RouteScoringType.BALANCED:  return <Scale className="w-4 h-4 text-yellow-400" />;
  }
}

function scoringLabel(type: RouteScoringType) {
  switch (type) {
    case RouteScoringType.FASTEST:   return 'Fastest';
    case RouteScoringType.SAFEST:    return 'Safest';
    case RouteScoringType.SMOOTHEST: return 'Smoothest';
    case RouteScoringType.BALANCED:  return 'Balanced';
  }
}

interface RouteCardProps {
  route: RouteOption;
  isActive: boolean;
  onNavigate: () => void;
}

function RouteCard({ route, isActive, onNavigate }: RouteCardProps) {
  const cong = congestionLabel(route.congestion_level);

  return (
    <div
      className={clsx(
        'rounded-xl border p-4 transition-all cursor-pointer',
        isActive
          ? 'border-blue-500 bg-blue-950/60'
          : 'border-gray-700 bg-gray-900 hover:border-gray-500'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {scoringIcon(route.scoring_type)}
          <span className="text-sm font-semibold text-white">
            {scoringLabel(route.scoring_type)}
          </span>
          {isActive && (
            <span className="text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded font-medium">
              Active
            </span>
          )}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="flex items-center gap-1.5">
          <Route className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-sm text-white font-medium">
            {route.distance_km.toFixed(1)} km
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-sm text-white font-medium">
            {route.estimated_time_min} min
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-sm text-white font-medium">
            {route.hazard_count} hazard{route.hazard_count !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Gauge className="w-3.5 h-3.5 text-gray-400" />
          <span className={`text-sm font-medium ${cong.color}`}>{cong.label}</span>
        </div>
      </div>

      {/* Quality bar */}
      <div className="mb-3">
        <div className="text-xs text-gray-400 mb-1">Road quality</div>
        {qualityBar(route.road_quality_score)}
      </div>

      {/* Navigate button */}
      <button
        onClick={(e) => { e.stopPropagation(); onNavigate(); }}
        className={clsx(
          'w-full py-1.5 rounded-lg text-sm font-medium flex items-center justify-center gap-1.5 transition-colors',
          isActive
            ? 'bg-blue-600 hover:bg-blue-700 text-white'
            : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
        )}
      >
        <Navigation className="w-3.5 h-3.5" />
        {isActive ? 'Navigating' : 'Navigate'}
      </button>
    </div>
  );
}

interface RoutePanelProps {
  routes: RouteOption[];
}

export default function RoutePanel({ routes }: RoutePanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const activeRoute    = useMapStore((s) => s.activeRoute);
  const setActiveRoute = useMapStore((s) => s.setActiveRoute);

  if (routes.length === 0) return null;

  return (
    <div
      className={clsx(
        'absolute top-4 left-4 z-[1000] flex flex-col transition-all duration-300',
        collapsed ? 'w-10' : 'w-72'
      )}
    >
      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="mb-2 self-end bg-gray-900 border border-gray-700 rounded-full p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 transition-colors shadow"
        aria-label={collapsed ? 'Expand route panel' : 'Collapse route panel'}
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>

      {!collapsed && (
        <div className="flex flex-col gap-2 overflow-y-auto max-h-[calc(100vh-10rem)]
          scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-700">
          <div className="text-xs font-semibold uppercase tracking-wider text-gray-400 px-1 mb-1">
            Route Options
          </div>
          {routes.map((r) => (
            <RouteCard
              key={r.id}
              route={r}
              isActive={activeRoute?.id === r.id}
              onNavigate={() => setActiveRoute(r)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
