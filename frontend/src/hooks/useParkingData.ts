import { useQuery } from '@tanstack/react-query';
import { fetchParkingAvailability } from '@/api/client';
import { useMapStore } from '@/store/mapStore';

// ─── Poll parking availability near a GPS coordinate ─────────────────────────

export function useParkingAvailability(
  lat: number | null,
  lon: number | null,
  radius = 500
) {
  const setParkingObservations = useMapStore((s) => s.setParkingObservations);

  const query = useQuery({
    queryKey: ['parking', lat, lon, radius],
    queryFn: async () => {
      const obs = await fetchParkingAvailability(lat!, lon!, radius);
      setParkingObservations(obs);
      return obs;
    },
    enabled: lat !== null && lon !== null,
    refetchInterval: 60_000,
    staleTime: 50_000,
  });

  return {
    data:      query.data ?? [],
    isLoading: query.isLoading,
    isError:   query.isError,
  };
}
