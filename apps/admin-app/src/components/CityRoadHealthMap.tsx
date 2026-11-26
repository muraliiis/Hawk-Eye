import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { CheckCircle2, Copy, Download, Eye, Globe, Layers, X, XCircle } from 'lucide-react';
import {
  BASEMAP_OPTIONS,
  buildQgisWmsTileUrl,
  createCirclePolygon,
  getBasemapStyle,
  toLngLat,
  type BasemapId,
} from '@shared/mapConfig';
import {
  CATEGORY_META,
  SOURCE_TYPE_META,
  formatUtcTime,
  type EdgeUnit,
  type ParkingSegment,
  type RoadEventRecord,
  type RoadSegment,
  type WorkflowStatus,
} from '@shared/types';

interface CityRoadHealthMapProps {
  theme: 'dark' | 'light';
  segments: RoadSegment[];
  events: RoadEventRecord[];
  parking: ParkingSegment[];
  fleet: EdgeUnit[];
  selectedEvent: RoadEventRecord | null;
  onSelectEvent: (event: RoadEventRecord | null) => void;
  onModerateEvent: (
    eventId: string,
    status: WorkflowStatus,
    severity?: 'low' | 'medium' | 'high',
  ) => Promise<void>;
}

export function CityRoadHealthMap({
  theme,
  segments,
  events,
  parking,
  fleet,
  selectedEvent,
  onSelectEvent,
  onModerateEvent,
}: CityRoadHealthMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const currentStyleRef = useRef<BasemapId>(theme === 'dark' ? 'dark' : 'positron');

  const [basemapOverride, setBasemapOverride] = useState<'auto' | BasemapId>('auto');
  const [is3D, setIs3D] = useState(true);
  const [styleTick, setStyleTick] = useState(0);

  const [showRoadQuality, setShowRoadQuality] = useState(true);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showHazards, setShowHazards] = useState(true);
  const [showParking, setShowParking] = useState(false);
  const [showFleet, setShowFleet] = useState(true);

  const [showQgisPanel, setShowQgisPanel] = useState(false);
  const [wmsUrl, setWmsUrl] = useState('https://ows.terrestris.de/osm/service');
  const [wmsLayers, setWmsLayers] = useState('OSM-WMS');
  const [wmsActive, setWmsActive] = useState(false);
  const [copiedFeed, setCopiedFeed] = useState<string | null>(null);

  const effectiveBasemap: BasemapId =
    basemapOverride === 'auto' ? (theme === 'dark' ? 'dark' : 'positron') : basemapOverride;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const initialStyle = effectiveBasemap;
    const map = new maplibregl.Map({
      container: el,
      style: getBasemapStyle(initialStyle) as string | maplibregl.StyleSpecification,
      center: [77.614, 12.961],
      zoom: 13.1,
      pitch: 32,
      bearing: -6,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');

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
    currentStyleRef.current = initialStyle;

    return () => {
      ro.disconnect();
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      popup.remove();
      map.remove();
      mapRef.current = null;
      popupRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || currentStyleRef.current === effectiveBasemap) return;
    currentStyleRef.current = effectiveBasemap;
    map.setStyle(getBasemapStyle(effectiveBasemap) as string | maplibregl.StyleSpecification);
  }, [effectiveBasemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({ pitch: is3D ? 34 : 0, bearing: is3D ? -6 : 0, duration: 450 });
  }, [is3D]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Optional QGIS Server / OGC WMS overlay layer
    if (map.getLayer('qgis-wms-layer')) map.removeLayer('qgis-wms-layer');
    if (map.getSource('qgis-wms-source')) map.removeSource('qgis-wms-source');

    if (wmsActive && wmsUrl.trim() && wmsLayers.trim()) {
      const wmsTile = buildQgisWmsTileUrl(wmsUrl, wmsLayers);
      map.addSource('qgis-wms-source', {
        type: 'raster',
        tiles: [wmsTile],
        tileSize: 256,
      });
      map.addLayer({
        id: 'qgis-wms-layer',
        type: 'raster',
        source: 'qgis-wms-source',
        paint: { 'raster-opacity': 0.55 },
      });
    }

    const setOrUpdateSource = (id: string, data: GeoJSON.FeatureCollection) => {
      const existing = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
      if (existing) existing.setData(data);
      else map.addSource(id, { type: 'geojson', data });
    };

    // Road segments
    const segFeatures: GeoJSON.Feature[] =
      showRoadQuality || showTraffic
        ? segments.map((seg) => {
            let color = '#10B981';
            if (seg.closed) color = '#EF4444';
            else if (showTraffic && seg.traffic.is_congested) color = '#9333EA';
            else if (showRoadQuality && seg.road_quality_penalty + seg.hazard_penalty > 6) color = '#F59E0B';
            else if (!showRoadQuality && showTraffic && seg.traffic.congestion_ratio >= 0.25) color = '#F59E0B';

            return {
              type: 'Feature',
              properties: { color, closed: seg.closed ? 1 : 0 },
              geometry: { type: 'LineString', coordinates: seg.polyline.map(toLngLat) },
            };
          })
        : [];
    setOrUpdateSource('admin-segments', { type: 'FeatureCollection', features: segFeatures });

    if (!map.getLayer('admin-segments-line')) {
      map.addLayer({
        id: 'admin-segments-line',
        type: 'line',
        source: 'admin-segments',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['==', ['get', 'closed'], 1], 5.5, 4.2],
          'line-opacity': 0.85,
        },
      });
    }

    // Parking corridors
    const parkFeatures: GeoJSON.Feature[] = showParking
      ? parking.map((p) => ({
          type: 'Feature',
          properties: { color: p.available_spaces >= 5 ? '#10B981' : '#F59E0B' },
          geometry: { type: 'LineString', coordinates: p.polyline.map(toLngLat) },
        }))
      : [];
    setOrUpdateSource('admin-parking', { type: 'FeatureCollection', features: parkFeatures });
    if (!map.getLayer('admin-parking-line')) {
      map.addLayer({
        id: 'admin-parking-line',
        type: 'line',
        source: 'admin-parking',
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 7.5, 'line-opacity': 0.85 },
      });
    }

    // Hazard uncertainty halos
    const activeEvents = showHazards
      ? events.filter((e) => e.workflow_status !== 'dismissed' && e.workflow_status !== 'resolved')
      : [];
    const haloFeatures: GeoJSON.Feature[] = activeEvents.map((evt) => ({
      type: 'Feature',
      properties: {
        color: CATEGORY_META[evt.category].color,
        selected: selectedEvent?.event_id === evt.event_id ? 1 : 0,
      },
      geometry: {
        type: 'Polygon',
        coordinates: [
          createCirclePolygon(
            evt.location.longitude,
            evt.location.latitude,
            Math.max(12, evt.location_accuracy_m * 3),
          ),
        ],
      },
    }));
    setOrUpdateSource('admin-halos', { type: 'FeatureCollection', features: haloFeatures });
    if (!map.getLayer('admin-halos-fill')) {
      map.addLayer({
        id: 'admin-halos-fill',
        type: 'fill',
        source: 'admin-halos',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': ['case', ['==', ['get', 'selected'], 1], 0.28, 0.12],
        },
      });
    }
    if (!map.getLayer('admin-halos-line')) {
      map.addLayer({
        id: 'admin-halos-line',
        type: 'line',
        source: 'admin-halos',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['==', ['get', 'selected'], 1], 2, 1],
          'line-opacity': 0.65,
        },
      });
    }

    // Markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    const popup = popupRef.current;

    for (const evt of activeEvents) {
      const cat = CATEGORY_META[evt.category];
      const src = SOURCE_TYPE_META[evt.source_type];
      const isSel = selectedEvent?.event_id === evt.event_id;

      const el = document.createElement('div');
      el.style.cssText = `width:26px;height:26px;border-radius:50%;background:${
        theme === 'dark' ? '#09101D' : '#FFFFFF'
      };border:2.5px solid ${cat.color};color:${cat.color};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;cursor:pointer;box-shadow:0 3px 10px rgba(0,0,0,0.45);${
        isSel ? 'transform:scale(1.22);' : ''
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
            `<strong>${cat.label}</strong> (${evt.workflow_status})<br/>Source: ${
              src.label
            }<br/>Conf: ${Math.round(evt.confidence * 100)}% · ±${evt.location_accuracy_m}m`,
          )
          .addTo(map);
      });
      el.addEventListener('mouseleave', () => popup?.remove());

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([evt.location.longitude, evt.location.latitude])
        .addTo(map);
      markersRef.current.push(marker);
    }

    if (showFleet) {
      for (const unit of fleet) {
        const isDegraded = unit.gnss_age_ms > unit.gnss_max_alignment_ms;
        const color = isDegraded ? '#EF4444' : '#22D3EE';
        const el = document.createElement('div');
        el.style.cssText = `width:22px;height:22px;border-radius:6px;background:${color};color:#031118;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;border:2px solid #FFFFFF;box-shadow:0 2px 8px rgba(0,0,0,0.45);`;
        el.textContent = 'V';
        el.addEventListener('mouseenter', () => {
          popup
            ?.setLngLat([unit.longitude, unit.latitude])
            .setHTML(
              `<strong>${unit.unit_id}</strong> (${unit.vehicle_label})<br/>GNSS age: ${unit.gnss_age_ms}ms · ${unit.fps} FPS`,
            )
            .addTo(map);
        });
        el.addEventListener('mouseleave', () => popup?.remove());
        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([unit.longitude, unit.latitude])
          .addTo(map);
        markersRef.current.push(marker);
      }
    }
  }, [
    styleTick,
    theme,
    segments,
    events,
    parking,
    fleet,
    showRoadQuality,
    showTraffic,
    showHazards,
    showParking,
    showFleet,
    selectedEvent,
    onSelectEvent,
    wmsActive,
    wmsUrl,
    wmsLayers,
  ]);

  const backendOrigin = `${window.location.protocol}//${window.location.hostname}:8000`;

  const copyFeedUrl = async (path: string) => {
    const full = `${backendOrigin}${path}`;
    try {
      await navigator.clipboard.writeText(full);
      setCopiedFeed(path);
      window.setTimeout(() => setCopiedFeed(null), 1800);
    } catch {
      // ignore clipboard block
    }
  };

  return (
    <div className="map-command-wrap">
      <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
        <div className="layer-bar">
          <button
            type="button"
            className={`layer-chip ${showRoadQuality ? 'on' : ''}`}
            onClick={() => setShowRoadQuality((v) => !v)}
          >
            Road Quality
          </button>
          <button
            type="button"
            className={`layer-chip ${showTraffic ? 'on' : ''}`}
            onClick={() => setShowTraffic((v) => !v)}
          >
            Traffic Congestion
          </button>
          <button
            type="button"
            className={`layer-chip ${showHazards ? 'on' : ''}`}
            onClick={() => setShowHazards((v) => !v)}
          >
            Hazards + Uncertainty
          </button>
          <button
            type="button"
            className={`layer-chip ${showParking ? 'on' : ''}`}
            onClick={() => setShowParking((v) => !v)}
          >
            Parking Corridors
          </button>
          <button
            type="button"
            className={`layer-chip ${showFleet ? 'on' : ''}`}
            onClick={() => setShowFleet((v) => !v)}
          >
            Edge Fleet
          </button>

          <select
            className="input-control"
            style={{ padding: '4px 8px', fontSize: 11.5, borderRadius: 999 }}
            value={basemapOverride}
            onChange={(e) => setBasemapOverride(e.target.value as 'auto' | BasemapId)}
            title="Select OpenFreeMap 3D Vector or Satellite style"
          >
            <option value="auto">Basemap: Theme Auto</option>
            {BASEMAP_OPTIONS.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}
              </option>
            ))}
          </select>

          <button
            type="button"
            className={`layer-chip ${is3D ? 'on' : ''}`}
            onClick={() => setIs3D((v) => !v)}
          >
            <Layers size={11} style={{ verticalAlign: 'middle', marginRight: 3 }} />
            {is3D ? '3D Tilt' : '2D'}
          </button>

          <button
            type="button"
            className={`layer-chip ${showQgisPanel || wmsActive ? 'on' : ''}`}
            onClick={() => setShowQgisPanel((v) => !v)}
          >
            <Globe size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            QGIS / WMS
          </button>
        </div>

        {showQgisPanel && (
          <div className="qgis-popover">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="panel-title">QGIS Desktop &amp; OGC WMS Integration</span>
              <button type="button" className="btn" onClick={() => setShowQgisPanel(false)} style={{ padding: '4px 7px' }}>
                <X size={13} />
              </button>
            </div>

            <a
              href="/api/gis/qgis-project.qgs"
              download="roadsense-bengaluru.qgs"
              className="btn primary"
              style={{ textDecoration: 'none', justifyContent: 'center' }}
            >
              <Download size={14} /> Download QGIS Project (.qgs)
            </a>

            <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
              Or connect live GeoJSON layers in QGIS Desktop (<em>Layer → Add Vector Layer → Protocol: HTTP</em>):
            </div>

            {['/api/gis/events.geojson', '/api/gis/segments.geojson', '/api/gis/parking.geojson'].map((path) => (
              <div
                key={path}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                  padding: '5px 8px',
                  borderRadius: 8,
                  background: 'var(--bg-elevated)',
                  fontSize: 11,
                }}
              >
                <span className="mono">{path}</span>
                <button type="button" className="btn" onClick={() => void copyFeedUrl(path)} style={{ padding: '3px 8px' }}>
                  <Copy size={11} /> {copiedFeed === path ? 'Copied' : 'Copy URL'}
                </button>
              </div>
            ))}

            <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 10, display: 'grid', gap: 6 }}>
              <div className="panel-title" style={{ fontSize: 11 }}>
                Overlay QGIS Server / OGC WMS Layer
              </div>
              <input
                type="text"
                className="input-control"
                value={wmsUrl}
                onChange={(e) => setWmsUrl(e.target.value)}
                placeholder="WMS Service URL (e.g. http://localhost:8081/cgi-bin/qgis_mapserv.fcgi)"
              />
              <input
                type="text"
                className="input-control"
                value={wmsLayers}
                onChange={(e) => setWmsLayers(e.target.value)}
                placeholder="WMS Layer Name(s)"
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className={`btn ${wmsActive ? 'danger' : 'primary'}`}
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => setWmsActive((v) => !v)}
                >
                  {wmsActive ? 'Disable WMS Overlay' : 'Enable WMS Overlay'}
                </button>
              </div>
            </div>
          </div>
        )}

        <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      </div>

      {selectedEvent && (
        <aside className="inspector-drawer">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="panel-title">RoadEvent v{selectedEvent.schema_version} Inspector</span>
            <button type="button" className="btn" onClick={() => onSelectEvent(null)}>
              <X size={14} />
            </button>
          </div>

          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span
              className="badge"
              style={{
                background: CATEGORY_META[selectedEvent.category].bg,
                color: CATEGORY_META[selectedEvent.category].color,
              }}
            >
              {CATEGORY_META[selectedEvent.category].label}
            </span>
            <span
              className="badge"
              style={{
                background: SOURCE_TYPE_META[selectedEvent.source_type].bg,
                color: SOURCE_TYPE_META[selectedEvent.source_type].color,
              }}
            >
              {SOURCE_TYPE_META[selectedEvent.source_type].label}
            </span>
            <span className="badge" style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
              {selectedEvent.workflow_status.toUpperCase()}
            </span>
          </div>

          <div className="panel-card" style={{ padding: 12, fontSize: 12, display: 'grid', gap: 6 }}>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Event ID: </span>
              <span className="mono">{selectedEvent.event_id}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-secondary)' }}>Segment: </span>
              <span className="mono">{selectedEvent.road_segment_id || 'Unassigned'}</span>
            </div>
            <div className="tabular">
              <span style={{ color: 'var(--text-secondary)' }}>Confidence: </span>
              <strong>{Math.round(selectedEvent.confidence * 100)}%</strong> ·{' '}
              <span style={{ color: 'var(--text-secondary)' }}>Uncertainty: </span>
              <strong>±{selectedEvent.location_accuracy_m} m</strong>
            </div>
            <div className="tabular">
              <span style={{ color: 'var(--text-secondary)' }}>Observed UTC: </span>
              <span>{formatUtcTime(selectedEvent.observed_at)}</span>
            </div>
            <div className="tabular">
              <span style={{ color: 'var(--text-secondary)' }}>Driver Feedback: </span>
              <span>
                {selectedEvent.confirmations} confirms · {selectedEvent.dismissals} cleared
              </span>
            </div>
          </div>

          <div>
            <div className="panel-title" style={{ marginBottom: 6 }}>
              Sanitized Attributes (0 PII)
            </div>
            <pre
              className="mono"
              style={{
                margin: 0,
                padding: 10,
                borderRadius: 8,
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-subtle)',
                fontSize: 11,
                overflowX: 'auto',
              }}
            >
              {JSON.stringify(selectedEvent.attributes, null, 2)}
            </pre>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div className="panel-title">Triage Actions</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn success"
                style={{ flex: 1 }}
                onClick={() => onModerateEvent(selectedEvent.event_id, 'verified')}
              >
                <CheckCircle2 size={14} /> Verify
              </button>
              <button
                type="button"
                className="btn"
                style={{ flex: 1 }}
                onClick={() => onModerateEvent(selectedEvent.event_id, 'resolved')}
              >
                <Eye size={14} /> Resolve
              </button>
              <button
                type="button"
                className="btn danger"
                style={{ flex: 1 }}
                onClick={() => onModerateEvent(selectedEvent.event_id, 'dismissed')}
              >
                <XCircle size={14} /> Dismiss
              </button>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
