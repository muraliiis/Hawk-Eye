import { useQuery } from '@tanstack/react-query';
import { fetchRoadEvents, fetchNearbyEvents } from '@/api/client';
import { useMapStore } from '@/store/mapStore';
import type { BBox } from '@/types';

// ─── Poll road events within a bounding box ───────────────────────────────────

export function useRoadEvents(bbox?: BBox) {
  const setRoadEvents = useMapStore((s) => s.setRoadEvents);

  return useQuery({
    queryKey: ['roadEvents', bbox],
    queryFn: async () => {
      const events = await fetchRoadEvents(bbox);
      setRoadEvents(events);
      return events;
    },
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

// ─── Poll road events near a GPS coordinate ───────────────────────────────────

export function useNearbyEvents(
  lat: number | null,
  lon: number | null,
  radius = 1000
) {
  const setRoadEvents = useMapStore((s) => s.setRoadEvents);

  return useQuery({
    queryKey: ['nearbyEvents', lat, lon, radius],
    queryFn: async () => {
      const events = await fetchNearbyEvents(lat!, lon!, radius);
      setRoadEvents(events);
      return events;
    },
    enabled: lat !== null && lon !== null,
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}
