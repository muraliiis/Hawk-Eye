import { useEffect } from 'react';
import { X, AlertTriangle, AlertOctagon, Info, Flame } from 'lucide-react';
import clsx from 'clsx';
import { useMapStore } from '@/store/mapStore';
import { SeverityLevel } from '@/types';
import type { HazardAlert } from '@/types';
import { formatDistanceToNow } from 'date-fns';

const AUTO_DISMISS_MS = 10_000;

function severityMeta(sev: SeverityLevel) {
  switch (sev) {
    case SeverityLevel.CRITICAL:
      return {
        icon: <Flame className="w-4 h-4" />,
        bg: 'bg-red-950 border-red-700',
        badge: 'bg-red-700 text-white',
        label: 'CRITICAL',
      };
    case SeverityLevel.HIGH:
      return {
        icon: <AlertOctagon className="w-4 h-4" />,
        bg: 'bg-orange-950 border-orange-700',
        badge: 'bg-orange-600 text-white',
        label: 'HIGH',
      };
    case SeverityLevel.MEDIUM:
      return {
        icon: <AlertTriangle className="w-4 h-4" />,
        bg: 'bg-yellow-950 border-yellow-600',
        badge: 'bg-yellow-500 text-black',
        label: 'MEDIUM',
      };
    default:
      return {
        icon: <Info className="w-4 h-4" />,
        bg: 'bg-gray-900 border-gray-600',
        badge: 'bg-gray-600 text-white',
        label: 'LOW',
      };
  }
}

interface AlertItemProps {
  alert: HazardAlert;
  onDismiss: (id: string) => void;
}

function AlertItem({ alert, onDismiss }: AlertItemProps) {
  const meta = severityMeta(alert.severity);

  useEffect(() => {
    const timer = setTimeout(() => onDismiss(alert.id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [alert.id, onDismiss]);

  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-3 rounded-lg border animate-slide-in-right',
        'w-80 shadow-xl',
        meta.bg
      )}
    >
      <div className="text-orange-300 mt-0.5 shrink-0">{meta.icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className={clsx('text-xs font-bold px-1.5 py-0.5 rounded', meta.badge)}>
            {meta.label}
          </span>
          <span className="text-xs text-gray-400 truncate">
            {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
          </span>
        </div>
        <p className="text-sm text-gray-200 leading-snug">{alert.message}</p>
      </div>
      <button
        onClick={() => onDismiss(alert.id)}
        className="shrink-0 text-gray-500 hover:text-white transition-colors mt-0.5"
        aria-label="Dismiss alert"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export default function HazardAlert() {
  const hazardAlerts  = useMapStore((s) => s.hazardAlerts);
  const dismissAlert  = useMapStore((s) => s.dismissHazardAlert);

  if (hazardAlerts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[1000] flex flex-col gap-2 pointer-events-none">
      {hazardAlerts.map((alert) => (
        <div key={alert.id} className="pointer-events-auto">
          <AlertItem alert={alert} onDismiss={dismissAlert} />
        </div>
      ))}
    </div>
  );
}
