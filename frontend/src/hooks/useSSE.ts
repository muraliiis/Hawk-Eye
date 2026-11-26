import { useEffect, useRef } from 'react';
import { useMapStore } from '@/store/mapStore';
import { SeverityLevel } from '@/types';

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

export function useSSEStream() {
  const addHazardAlert = useMapStore((s) => s.addHazardAlert);
  const esRef          = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(`${API_URL}/api/stream`);
    esRef.current = es;

    es.addEventListener('road_event', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as {
          id?: string;
          event_type?: string;
          category?: string;
          severity?: string;
        };
        // Add as hazard alert if high or critical severity
        if (
          data.severity === 'high' ||
          data.severity === 'HIGH' ||
          data.severity === 'critical' ||
          data.severity === 'CRITICAL'
        ) {
          addHazardAlert({
            id:         data.id ?? crypto.randomUUID(),
            message:    `${data.event_type ?? data.category ?? 'Event'} detected`,
            severity:   (data.severity?.toUpperCase() as SeverityLevel) ?? SeverityLevel.HIGH,
            created_at: new Date().toISOString(),
          });
        }
      } catch {
        // malformed SSE frame — ignore
      }
    });

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
    // addHazardAlert is a stable Zustand selector — safe to omit
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // expose ref so callers can close manually if needed
  return esRef;
}
