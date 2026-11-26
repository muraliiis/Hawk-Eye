import type { GraphNode, RouteComparisonItem } from './types';

type OsrmRouteResponse = {
  code: string;
  routes?: Array<{
    geometry?: {
      type: 'LineString';
      coordinates: Array<[number, number]>;
    };
  }>;
};

const configuredBase = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_OSRM_BASE_URL;
const OSRM_BASE_URL = (configuredBase || 'https://router.project-osrm.org').replace(/\/$/, '');

const roadGeometryCache = new Map<string, [number, number][]>();

/**
 * Resolves display geometry against a road graph with local caching so SSE
 * updates never spam OSRM, and degrades cleanly when offline.
 */
export async function resolveRoadGeometry(
  route: RouteComparisonItem,
  nodesById: Map<string, GraphNode>,
  signal?: AbortSignal,
): Promise<RouteComparisonItem> {
  const waypoints = route.nodes
    .map((nodeId) => nodesById.get(nodeId))
    .filter((node): node is GraphNode => node !== undefined);

  if (waypoints.length < 2) {
    return { ...route, geometry_source: 'seed-fallback' };
  }

  const cacheKey = route.nodes.join('>');
  const cached = roadGeometryCache.get(cacheKey);
  if (cached) {
    return {
      ...route,
      polyline: cached,
      geometry_source: 'road-network',
    };
  }

  const coordinates = waypoints.map((node) => `${node.longitude},${node.latitude}`).join(';');
  const url = new URL(`${OSRM_BASE_URL}/route/v1/driving/${coordinates}`);
  url.searchParams.set('overview', 'full');
  url.searchParams.set('geometries', 'geojson');
  url.searchParams.set('steps', 'false');
  url.searchParams.set('continue_straight', 'false');

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4500);
  const onParentAbort = () => controller.abort();
  signal?.addEventListener('abort', onParentAbort);

  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`routing service returned ${response.status}`);
    const payload = (await response.json()) as OsrmRouteResponse;
    const geometry = payload.routes?.[0]?.geometry;
    if (payload.code !== 'Ok' || geometry?.type !== 'LineString' || geometry.coordinates.length < 2) {
      throw new Error('routing service did not return a usable road geometry');
    }

    const mapped = geometry.coordinates.map(
      ([longitude, latitude]) => [latitude, longitude] as [number, number],
    );
    roadGeometryCache.set(cacheKey, mapped);
    return {
      ...route,
      polyline: mapped,
      geometry_source: 'road-network',
    };
  } catch (error) {
    if (signal?.aborted) throw error;
    return { ...route, geometry_source: 'seed-fallback' };
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', onParentAbort);
  }
}
