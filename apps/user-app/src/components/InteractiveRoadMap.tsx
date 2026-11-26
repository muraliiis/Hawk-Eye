import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Layers } from 'lucide-react';
import {
  BASEMAP_OPTIONS,
  createCirclePolygon,
  getBasemapStyle,
  toLngLat,
  type BasemapId,
} from '@shared/mapConfig';
import {
  CATEGORY_META,
  SOURCE_TYPE_META,
  type GraphNode,
  type ParkingSegment,
  type RoadEventRecord,
  type RoadSegment,
  type RouteComparisonItem,
} from '@shared/types';

interface InteractiveRoadMapProps {
  nodes: GraphNode[];
  segments: RoadSegment[];
  events: RoadEventRecord[];
  routes: RouteComparisonItem[];
  selectedProfile: string;
  parking: ParkingSegment[];
  showParkingLayer: boolean;
  navigating: boolean;
  vehiclePosition: [number, number] | null;
  vehicleBearing: number;
  selectedEventId: string | null;
  onSelectEvent: (event: RoadEventRecord) => void;
}

export function InteractiveRoadMap({
  nodes,
  segments,
  events,
  routes,
  selectedProfile,
  parking,
  showParkingLayer,
  navigating,
  vehiclePosition,
  vehicleBearing,
  selectedEventId,
  onSelectEvent,
}: InteractiveRoadMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const vehicleMarkerRef = useRef<maplibregl.Marker | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const currentStyleRef = useRef<BasemapId>('dark');

  const [basemap, setBasemap] = useState<BasemapId>('dark');
  const [is3D, setIs3D] = useState(true);
  const [styleTick, setStyleTick] = useState(0);

  // Initialize MapLibre 3D Vector Map once
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const map = new maplibregl.Map({
      container: el,
      style: getBasemapStyle('dark') as string | maplibregl.StyleSpecification,
      center: [77.614, 12.961],
      zoom: 13.1,
      pitch: 36,
      bearing: -8,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');

    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 14,
    });

    map.on('style.load', () => {
      setStyleTick((t) => t + 1);
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);

    mapRef.current = map;
    popupRef.current = popup;
    currentStyleRef.current = 'dark';

    return () => {
      ro.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      vehicleMarkerRef.current?.remove();
      vehicleMarkerRef.current = null;
      popup.remove();
      map.remove();
      mapRef.current = null;
      popupRef.current = null;
    };
  }, []);

  // Switch basemap style dynamically
  useEffect(() => {
    const map = mapRef.current;
    if (!map || currentStyleRef.current === basemap) return;
    currentStyleRef.current = basemap;
    map.setStyle(getBasemapStyle(basemap) as string | maplibregl.StyleSpecification);
  }, [basemap]);

  // Update 3D camera pitch when 3D toggle changes (outside active navigation follow mode)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || navigating) return;
    map.easeTo({ pitch: is3D ? 38 : 0, bearing: is3D ? -8 : 0, duration: 500 });
  }, [is3D, navigating]);

  // Render GeoJSON layers & custom markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const setOrUpdateSource = (id: string, data: GeoJSON.FeatureCollection) => {
      const existing = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(data);
      } else {
        map.addSource(id, { type: 'geojson', data });
      }
    };

    // 1. Road segments
    const segFeatures: GeoJSON.Feature[] = segments.map((seg) => {
      let color = '#475569';
      if (seg.closed) color = '#EF4444';
      else if (seg.traffic.is_congested) color = '#9333EA';
      else if (seg.road_quality_penalty + seg.hazard_penalty > 6) color = '#D97706';
      return {
        type: 'Feature',
        properties: {
          color,
          closed: seg.closed ? 1 : 0,
          name: seg.name,
          mean: seg.traffic.mean_speed_kph,
          legal: seg.legal_speed_limit_kph,
        },
        geometry: {
          type: 'LineString',
          coordinates: seg.polyline.map(toLngLat),
        },
      };
    });
    setOrUpdateSource('road-segments', { type: 'FeatureCollection', features: segFeatures });

    if (!map.getLayer('road-segments-line')) {
      map.addLayer({
        id: 'road-segments-line',
        type: 'line',
        source: 'road-segments',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['==', ['get', 'closed'], 1], 4.5, 3.2],
          'line-opacity': 0.72,
        },
      });
    }

    // 2. Alternative routes (dashed)
    const roadConstrainedRoutes = routes;

    const altFeatures: GeoJSON.Feature[] = roadConstrainedRoutes
      .filter((r) => r.profile !== selectedProfile)
      .map((alt) => ({
        type: 'Feature',
        properties: { profile: alt.profile },
        geometry: {
          type: 'LineString',
          coordinates: alt.polyline.map(toLngLat),
        },
      }));
    setOrUpdateSource('alt-routes', { type: 'FeatureCollection', features: altFeatures });

    if (!map.getLayer('alt-routes-line')) {
      map.addLayer({
        id: 'alt-routes-line',
        type: 'line',
        source: 'alt-routes',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#64748B',
          'line-width': 3.5,
          'line-dasharray': [2, 2],
          'line-opacity': 0.48,
        },
      });
    }

    // 3. Active glowing route
    const activeRoute = roadConstrainedRoutes.find((r) => r.profile === selectedProfile);
    const activeColor =
      activeRoute && (activeRoute.profile === 'safest' || activeRoute.profile === 'smoothest')
        ? '#10B981'
        : '#22D3EE';
    const activeFeatures: GeoJSON.Feature[] = activeRoute
      ? [
          {
            type: 'Feature',
            properties: { color: activeColor },
            geometry: {
              type: 'LineString',
              coordinates: activeRoute.polyline.map(toLngLat),
            },
          },
        ]
      : [];
    setOrUpdateSource('active-route', { type: 'FeatureCollection', features: activeFeatures });

    if (!map.getLayer('active-route-glow')) {
      map.addLayer({
        id: 'active-route-glow',
        type: 'line',
        source: 'active-route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 13,
          'line-opacity': 0.25,
        },
      });
    }
    if (!map.getLayer('active-route-core')) {
      map.addLayer({
        id: 'active-route-core',
        type: 'line',
        source: 'active-route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 5.5,
          'line-opacity': 0.96,
        },
      });
    }

    // 4. Parking curb corridors
    const parkingFeatures: GeoJSON.Feature[] = showParkingLayer
      ? parking.map((bay) => ({
          type: 'Feature',
          properties: {
            color: bay.available_spaces >= 5 ? '#10B981' : bay.available_spaces >= 2 ? '#F59E0B' : '#EF4444',
          },
          geometry: {
            type: 'LineString',
            coordinates: bay.polyline.map(toLngLat),
          },
        }))
      : [];
    setOrUpdateSource('parking-bays', { type: 'FeatureCollection', features: parkingFeatures });

    if (!map.getLayer('parking-bays-line')) {
      map.addLayer({
        id: 'parking-bays-line',
        type: 'line',
        source: 'parking-bays',
        layout: { 'line-cap': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 7,
          'line-opacity': 0.85,
        },
      });
    }

    // 5. Hazard uncertainty halos (true metric radius from location_accuracy_m)
    const visibleEvents = events.filter((e) => e.workflow_status === 'active' || e.workflow_status === 'verified');
    const haloFeatures: GeoJSON.Feature[] = visibleEvents.map((evt) => ({
      type: 'Feature',
      properties: {
        color: CATEGORY_META[evt.category].color,
        selected: evt.event_id === selectedEventId ? 1 : 0,
      },
      geometry: {
        type: 'Polygon',
        coordinates: [
          createCirclePolygon(
            evt.location.longitude,
            evt.location.latitude,
            Math.max(15, evt.location_accuracy_m * 2.5),
          ),
        ],
      },
    }));
    setOrUpdateSource('hazard-halos', { type: 'FeatureCollection', features: haloFeatures });

    if (!map.getLayer('hazard-halos-fill')) {
      map.addLayer({
        id: 'hazard-halos-fill',
        type: 'fill',
        source: 'hazard-halos',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': ['case', ['==', ['get', 'selected'], 1], 0.28, 0.12],
        },
      });
    }
    if (!map.getLayer('hazard-halos-outline')) {
      map.addLayer({
        id: 'hazard-halos-outline',
        type: 'line',
        source: 'hazard-halos',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['==', ['get', 'selected'], 1], 2, 1],
          'line-opacity': 0.55,
        },
      });
    }

    // Clear and rebuild crisp HTML markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    const popup = popupRef.current;

    // Nodes
    for (const node of nodes) {
      const isEndpoint =
        activeRoute &&
        (activeRoute.nodes[0] === node.id || activeRoute.nodes[activeRoute.nodes.length - 1] === node.id);
      const el = document.createElement('div');
      el.style.cssText = `width:${isEndpoint ? 14 : 10}px;height:${isEndpoint ? 14 : 10}px;border-radius:50%;background:${
        isEndpoint ? '#22D3EE' : '#0E1522'
      };border:2px solid ${isEndpoint ? '#FFFFFF' : '#94A3B8'};box-shadow:0 2px 6px rgba(0,0,0,0.6);`;
      el.title = `${node.name} (${node.area})`;
      const m = new maplibregl.Marker({ element: el }).setLngLat([node.longitude, node.latitude]).addTo(map);
      markersRef.current.push(m);
    }

    // Parking badges
    if (showParkingLayer) {
      for (const bay of parking) {
        const bayColor = bay.available_spaces >= 5 ? '#10B981' : bay.available_spaces >= 2 ? '#F59E0B' : '#EF4444';
        const el = document.createElement('div');
        el.style.cssText = `background:#0B1220;border:2px solid ${bayColor};color:#F8FAFC;border-radius:999px;padding:2px 7px;font-size:11px;font-weight:800;box-shadow:0 4px 12px rgba(0,0,0,0.55);cursor:pointer;`;
        el.textContent = `P ${bay.available_spaces}`;
        el.addEventListener('mouseenter', () => {
          popup
            ?.setLngLat([bay.center.longitude, bay.center.latitude])
            .setHTML(
              `<strong>${bay.segment_name}</strong><br/>${bay.available_spaces} / ${bay.total_spaces_estimated} bays open (Privacy-Masked)`,
            )
            .addTo(map);
        });
        el.addEventListener('mouseleave', () => popup?.remove());
        const m = new maplibregl.Marker({ element: el })
          .setLngLat([bay.center.longitude, bay.center.latitude])
          .addTo(map);
        markersRef.current.push(m);
      }
    }

    // Hazard pins
    for (const evt of visibleEvents) {
      const cat = CATEGORY_META[evt.category];
      const src = SOURCE_TYPE_META[evt.source_type];
      const isSelected = evt.event_id === selectedEventId;

      const el = document.createElement('div');
      el.style.cssText = `width:28px;height:28px;border-radius:50%;background:#0B1220;border:2.5px solid ${
        cat.color
      };color:${cat.color};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,0.7);transition:transform 0.12s;${
        isSelected ? 'transform:scale(1.22);' : ''
      }`;
      el.textContent = cat.shortLabel;

      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onSelectEvent(evt);
      });
      el.addEventListener('mouseenter', () => {
        popup
          ?.setLngLat([evt.location.longitude, evt.location.latitude])
          .setHTML(
            `<strong>${cat.label}</strong> (${Math.round(evt.confidence * 100)}%)<br/>Source: ${
              src.label
            }<br/>±${evt.location_accuracy_m}m accuracy`,
          )
          .addTo(map);
      });
      el.addEventListener('mouseleave', () => popup?.remove());

      const m = new maplibregl.Marker({ element: el })
        .setLngLat([evt.location.longitude, evt.location.latitude])
        .addTo(map);
      markersRef.current.push(m);
    }
  }, [
    styleTick,
    nodes,
    segments,
    events,
    routes,
    selectedProfile,
    parking,
    showParkingLayer,
    selectedEventId,
    onSelectEvent,
  ]);

  // Live 3D Navigation Vehicle Marker + Smooth Heading Camera Follow
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!vehiclePosition) {
      vehicleMarkerRef.current?.remove();
      vehicleMarkerRef.current = null;
      return;
    }

    const lngLat: [number, number] = [vehiclePosition[1], vehiclePosition[0]];
    if (!vehicleMarkerRef.current) {
      const el = document.createElement('div');
      el.style.cssText =
        'width:32px;height:32px;border-radius:50%;background:rgba(34,211,238,0.24);display:flex;align-items:center;justify-content:center;';
      el.innerHTML =
        '<div style="width:16px;height:16px;border-radius:50%;background:#22D3EE;border:3px solid #FFFFFF;box-shadow:0 0 18px #22D3EE;"></div>';
      vehicleMarkerRef.current = new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map);
    } else {
      vehicleMarkerRef.current.setLngLat(lngLat);
    }

    if (navigating) {
      map.easeTo({
        center: lngLat,
        zoom: 15.6,
        pitch: is3D ? 58 : 0,
        bearing: vehicleBearing,
        duration: 240,
      });
    }
  }, [vehiclePosition, vehicleBearing, navigating, is3D]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {!navigating && (
        <div className="basemap-floating" role="group" aria-label="Basemap switcher">
          <Layers size={13} color="#22D3EE" style={{ marginLeft: 4 }} />
          {BASEMAP_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`basemap-chip ${basemap === opt.id ? 'active' : ''}`}
              onClick={() => setBasemap(opt.id)}
              title={opt.description}
            >
              {opt.label}
            </button>
          ))}
          <button
            type="button"
            className={`basemap-chip ${is3D ? 'active' : ''}`}
            onClick={() => setIs3D((v) => !v)}
            title="Toggle 3D tilt perspective"
          >
            {is3D ? '3D Tilt' : '2D'}
          </button>
        </div>
      )}
    </div>
  );
}
