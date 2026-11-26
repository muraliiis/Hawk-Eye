export type BasemapId = 'dark' | 'liberty' | 'positron' | 'satellite';

export interface RasterStyleConfig {
  version: 8;
  sources: Record<
    string,
    {
      type: 'raster';
      tiles: string[];
      tileSize: number;
      attribution?: string;
    }
  >;
  layers: Array<{
    id: string;
    type: 'raster';
    source: string;
    paint?: { 'raster-opacity'?: number };
  }>;
}

export const BASEMAP_OPTIONS: Array<{ id: BasemapId; label: string; description: string }> = [
  { id: 'dark', label: 'Dark HUD', description: 'OpenFreeMap Dark Vector' },
  { id: 'liberty', label: '3D Street', description: 'OpenFreeMap Liberty 3D Buildings' },
  { id: 'positron', label: 'Light Ops', description: 'OpenFreeMap Positron Vector' },
  { id: 'satellite', label: 'Satellite', description: 'Esri World Imagery + Labels' },
];

const SATELLITE_STYLE: RasterStyleConfig = {
  version: 8,
  sources: {
    'esri-imagery': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: 'Tiles © Esri',
    },
    'carto-labels': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/light_only_labels/{z}/{y}/{x}.png',
        'https://b.basemaps.cartocdn.com/light_only_labels/{z}/{y}/{x}.png',
      ],
      tileSize: 256,
    },
  },
  layers: [
    { id: 'esri-imagery-layer', type: 'raster', source: 'esri-imagery' },
    { id: 'carto-labels-layer', type: 'raster', source: 'carto-labels', paint: { 'raster-opacity': 0.9 } },
  ],
};

export function getBasemapStyle(id: BasemapId): string | RasterStyleConfig {
  if (id === 'satellite') return SATELLITE_STYLE;
  return `https://tiles.openfreemap.org/styles/${id}`;
}

export function toLngLat(latLon: [number, number]): [number, number] {
  return [latLon[1], latLon[0]];
}

export function createCirclePolygon(
  lon: number,
  lat: number,
  radiusMeters: number,
  steps = 36,
): [number, number][] {
  const earthRadius = 6371000;
  const latRad = (lat * Math.PI) / 180;
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const dLat = (radiusMeters * Math.cos(angle)) / earthRadius;
    const dLon = (radiusMeters * Math.sin(angle)) / (earthRadius * Math.cos(latRad));
    ring.push([lon + (dLon * 180) / Math.PI, lat + (dLat * 180) / Math.PI]);
  }
  return ring;
}

export function computeBearingDeg(fromLatLon: [number, number], toLatLon: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const lat1 = toRad(fromLatLon[0]);
  const lon1 = toRad(fromLatLon[1]);
  const lat2 = toRad(toLatLon[0]);
  const lon2 = toRad(toLatLon[1]);
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

export function buildQgisWmsTileUrl(wmsBaseUrl: string, layerName: string): string {
  const cleanBase = wmsBaseUrl.trim();
  const sep = cleanBase.includes('?') ? '&' : '?';
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    VERSION: '1.3.0',
    REQUEST: 'GetMap',
    LAYERS: layerName.trim(),
    STYLES: '',
    CRS: 'EPSG:3857',
    WIDTH: '256',
    HEIGHT: '256',
    FORMAT: 'image/png',
    TRANSPARENT: 'TRUE',
  });
  return `${cleanBase}${sep}${params.toString()}&BBOX={bbox-epsg-3857}`;
}
