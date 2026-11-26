import clsx from 'clsx';
import { Gauge, AlertTriangle, TrendingDown, TrendingUp } from 'lucide-react';
import { useMapStore } from '@/store/mapStore';

function speedStatus(current: number, limit: number, advisory: number) {
  if (current > limit)     return { label: 'Over Limit', color: 'text-red-400',    bg: 'bg-red-950   border-red-700' };
  if (current > advisory)  return { label: 'Advisory',   color: 'text-yellow-400', bg: 'bg-yellow-950 border-yellow-700' };
  return                          { label: 'Safe',        color: 'text-green-400',  bg: 'bg-gray-900   border-gray-700' };
}

export default function SpeedAdvisory() {
  const advisory = useMapStore((s) => s.speedAdvisory);

  if (!advisory) return null;

  const { current_speed_kmh, speed_limit_kmh, advisory_speed_kmh, reason, hazard_ahead, hazard_distance_m } = advisory;
  const status = speedStatus(current_speed_kmh, speed_limit_kmh, advisory_speed_kmh);
  const speedDiff = current_speed_kmh - speed_limit_kmh;

  return (
    <div
      className={clsx(
        'absolute top-4 left-1/2 -translate-x-1/2 z-[1000]',
        'flex flex-col items-center gap-1 px-5 py-3 rounded-2xl border shadow-xl',
        'min-w-[220px]',
        status.bg
      )}
    >
      {/* Speed display */}
      <div className="flex items-end gap-1">
        <span className={clsx('text-4xl font-bold tabular-nums', status.color)}>
          {Math.round(current_speed_kmh)}
        </span>
        <span className="text-gray-400 text-sm mb-1.5">km/h</span>
      </div>

      {/* Limit and advisory */}
      <div className="flex items-center gap-4 text-xs">
        <div className="flex items-center gap-1 text-gray-400">
          <Gauge className="w-3.5 h-3.5" />
          <span>Limit: <span className="text-white font-medium">{speed_limit_kmh}</span></span>
        </div>
        <div className="flex items-center gap-1 text-gray-400">
          {speedDiff > 0
            ? <TrendingUp className="w-3.5 h-3.5 text-red-400" />
            : <TrendingDown className="w-3.5 h-3.5 text-green-400" />}
          <span>Advisory: <span className="text-white font-medium">{advisory_speed_kmh}</span></span>
        </div>
      </div>

      {/* Status badge */}
      <span className={clsx('text-xs font-semibold mt-0.5', status.color)}>
        {status.label}
      </span>

      {/* Hazard warning */}
      {hazard_ahead && (
        <div className="flex items-center gap-1.5 mt-1 text-orange-400 text-xs font-medium bg-orange-950/60 px-2 py-1 rounded-lg border border-orange-800">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>
            Hazard ahead
            {hazard_distance_m != null && ` — ${hazard_distance_m}m`}
          </span>
        </div>
      )}

      {/* Reason text */}
      {reason && (
        <div className="text-xs text-gray-400 text-center mt-0.5 max-w-[180px] leading-tight">
          {reason}
        </div>
      )}
    </div>
  );
}
