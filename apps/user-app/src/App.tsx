import { useCallback, useEffect, useState } from 'react';
import { Camera, Car, Monitor, Navigation, Shield, Smartphone } from 'lucide-react';
import { api, subscribeRoadStream } from '@shared/api';
import { resolveRoadGeometry } from '@shared/roadRouting';
import type {
  GraphNode,
  ParkingSegment,
  RoadEventRecord,
  RoadSegment,
  RouteComparisonItem,
  RouteProfile,
} from '@shared/types';
import { ActiveNavigationHUD } from './components/ActiveNavigationHUD';
import { DashcamCaptureMode } from './components/DashcamCaptureMode';
import { InteractiveRoadMap } from './components/InteractiveRoadMap';
import { ParkingFinderDrawer } from './components/ParkingFinderDrawer';
import { RoutePlannerSheet } from './components/RoutePlannerSheet';
import { SafetyPrivacyPanel } from './components/SafetyPrivacyPanel';

type UserTab = 'navigate' | 'dashcam' | 'parking' | 'safety';

export default function App() {
  const [tab, setTab] = useState<UserTab>('navigate');
  const [phonePreview, setPhonePreview] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);

  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [segments, setSegments] = useState<RoadSegment[]>([]);
  const [events, setEvents] = useState<RoadEventRecord[]>([]);
  const [parking, setParking] = useState<ParkingSegment[]>([]);

  const [origin, setOrigin] = useState('cubbon');
  const [destination, setDestination] = useState('koramangala');
  const [routes, setRoutes] = useState<RouteComparisonItem[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<RouteProfile>('safest');
  const [loadingRoutes, setLoadingRoutes] = useState(false);
  const [routeGeometryWarning, setRouteGeometryWarning] = useState(false);

  const [navigating, setNavigating] = useState(false);
  const [vehiclePosition, setVehiclePosition] = useState<[number, number] | null>(null);
  const [vehicleBearing, setVehicleBearing] = useState(0);
  const [selectedEvent, setSelectedEvent] = useState<RoadEventRecord | null>(null);

  const [dashcamOptIn, setDashcamOptIn] = useState(true);
  const [telemetryOptIn, setTelemetryOptIn] = useState(true);
  const [audioChimesEnabled, setAudioChimesEnabled] = useState(true);

  const refreshRoutes = useCallback(async (orig: string, dest: string) => {
    if (!orig || !dest || orig === dest || nodes.length === 0) return;
    setLoadingRoutes(true);
    try {
      const res = await api.compareRoutes(orig, dest);
      const nodesById = new Map(nodes.map((node) => [node.id, node]));
      const resolved = await Promise.all(res.routes.map((route) => resolveRoadGeometry(route, nodesById)));
      setRoutes(resolved);
      setRouteGeometryWarning(resolved.some((route) => route.geometry_source !== 'road-network'));
    } finally {
      setLoadingRoutes(false);
    }
  }, [nodes]);

  const refreshWorld = useCallback(async () => {
    const [net, evts, park] = await Promise.all([api.getNetwork(), api.listEvents(), api.getParking()]);
    setNodes(net.nodes);
    setSegments(net.segments);
    setEvents(evts.events);
    setParking(park.segments);
  }, []);

  useEffect(() => {
    void refreshWorld();
  }, [refreshWorld]);

  useEffect(() => {
    void refreshRoutes(origin, destination);
  }, [origin, destination, refreshRoutes]);

  useEffect(() => {
    return subscribeRoadStream(
      () => {
        void refreshWorld();
        void refreshRoutes(origin, destination);
      },
      (connected) => setStreamConnected(connected),
    );
  }, [refreshWorld, refreshRoutes, origin, destination]);

  const handleFeedback = useCallback(
    async (eventId: string, action: 'confirm' | 'cleared') => {
      const res = await api.sendDriverFeedback(eventId, action);
      setSelectedEvent((prev) => (prev?.event_id === eventId ? res.event : prev));
      await refreshWorld();
      await refreshRoutes(origin, destination);
    },
    [refreshWorld, refreshRoutes, origin, destination],
  );

  const activeRoute = routes.find((route) => route.profile === selectedProfile) || routes[0] || null;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Navigation size={18} />
          </div>
          <div>
            <div className="brand-title">RoadSense Driver HUD</div>
            <div className="brand-sub">Safe Navigation · Edge Dashcam · Roadside Parking</div>
          </div>
        </div>

        <nav className="mode-tabs" aria-label="User app sections">
          <button
            type="button"
            className={`mode-tab ${tab === 'navigate' ? 'active' : ''}`}
            onClick={() => setTab('navigate')}
          >
            <Navigation size={14} /> Navigate
          </button>
          <button
            type="button"
            className={`mode-tab ${tab === 'dashcam' ? 'active' : ''}`}
            onClick={() => {
              setNavigating(false);
              setTab('dashcam');
            }}
          >
            <Camera size={14} /> Dashcam
          </button>
          <button
            type="button"
            className={`mode-tab ${tab === 'parking' ? 'active' : ''}`}
            onClick={() => {
              setNavigating(false);
              setTab('parking');
            }}
          >
            <Car size={14} /> Parking
          </button>
          <button
            type="button"
            className={`mode-tab ${tab === 'safety' ? 'active' : ''}`}
            onClick={() => {
              setNavigating(false);
              setTab('safety');
            }}
          >
            <Shield size={14} /> Safety
          </button>
        </nav>

        <div className="topbar-controls">
          <span className="pill-btn" title="Real-time RoadEvent SSE feed">
            <span className={`status-dot ${streamConnected ? 'online' : 'offline'}`} />
            {streamConnected ? 'Live Stream' : 'Connecting'}
          </span>
          <button
            type="button"
            className="pill-btn"
            onClick={() => setPhonePreview((p) => !p)}
            title="Switch between Full Cockpit and Mobile Phone Preview"
          >
            {phonePreview ? <Monitor size={14} /> : <Smartphone size={14} />}
            {phonePreview ? 'Cockpit View' : 'Mobile Frame'}
          </button>
        </div>
      </header>

      <main className={`workspace-stage ${phonePreview ? 'phone-frame' : ''}`}>
        <div className="viewport-container">
          {tab === 'dashcam' ? (
            <DashcamCaptureMode
              segments={segments}
              dashcamOptIn={dashcamOptIn}
              onEventPublished={() => {
                void refreshWorld();
                void refreshRoutes(origin, destination);
              }}
            />
          ) : (
            <>
              {!navigating && (
                <aside className="side-sheet">
                  {tab === 'navigate' && (
                    <RoutePlannerSheet
                      nodes={nodes}
                      origin={origin}
                      destination={destination}
                      onChangeOrigin={setOrigin}
                      onChangeDestination={setDestination}
                      onSwap={() => {
                        setOrigin(destination);
                        setDestination(origin);
                      }}
                      routes={routes}
                      selectedProfile={selectedProfile}
                      onSelectProfile={setSelectedProfile}
                      onStartNavigation={() => setNavigating(true)}
                      selectedEvent={selectedEvent}
                      onClearSelectedEvent={() => setSelectedEvent(null)}
                      onFeedback={handleFeedback}
                      loadingRoutes={loadingRoutes}
                      routeGeometryWarning={routeGeometryWarning}
                    />
                  )}
                  {tab === 'parking' && (
                    <ParkingFinderDrawer
                      parking={parking}
                      onNavigateToParking={(segId) => {
                        const seg = segments.find((s) => s.segment_id === segId);
                        if (seg) {
                          const target = seg.end === origin ? seg.start : seg.end;
                          setDestination(target);
                        }
                        setTab('navigate');
                      }}
                    />
                  )}
                  {tab === 'safety' && (
                    <SafetyPrivacyPanel
                      dashcamOptIn={dashcamOptIn}
                      onToggleDashcamOptIn={() => setDashcamOptIn((v) => !v)}
                      telemetryOptIn={telemetryOptIn}
                      onToggleTelemetryOptIn={() => setTelemetryOptIn((v) => !v)}
                      audioChimesEnabled={audioChimesEnabled}
                      onToggleAudioChimes={() => setAudioChimesEnabled((v) => !v)}
                    />
                  )}
                </aside>
              )}

              <section className="map-pane">
                <InteractiveRoadMap
                  nodes={nodes}
                  segments={segments}
                  events={events}
                  routes={routes}
                  selectedProfile={selectedProfile}
                  parking={parking}
                  showParkingLayer={tab === 'parking' || tab === 'navigate'}
                  navigating={navigating}
                  vehiclePosition={vehiclePosition}
                  vehicleBearing={vehicleBearing}
                  selectedEventId={selectedEvent?.event_id ?? null}
                  onSelectEvent={(evt) => setSelectedEvent(evt)}
                />

                {navigating && activeRoute && (
                  <ActiveNavigationHUD
                    route={activeRoute}
                    segments={segments}
                    audioChimesEnabled={audioChimesEnabled}
                    onToggleAudioChimes={() => setAudioChimesEnabled((v) => !v)}
                    onVehiclePositionChange={(pos, bearing) => {
                      setVehiclePosition(pos);
                      if (bearing !== undefined) setVehicleBearing(bearing);
                    }}
                    onFeedback={handleFeedback}
                    onExit={() => setNavigating(false)}
                  />
                )}
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

