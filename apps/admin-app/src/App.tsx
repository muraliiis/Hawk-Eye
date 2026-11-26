import { useCallback, useEffect, useState } from 'react';
import { Activity, Cpu, ListFilter, Map } from 'lucide-react';
import { api, subscribeRoadStream } from '@shared/api';
import type {
  FleetCompliancePayload,
  ParkingSegment,
  RoadEventRecord,
  RoadSegment,
  WorkflowStatus,
} from '@shared/types';
import { CityRoadHealthMap } from './components/CityRoadHealthMap';
import { EventTriageQueue } from './components/EventTriageQueue';
import { FleetSensorHealth } from './components/FleetSensorHealth';
import { TopCommandBar } from './components/TopCommandBar';
import { TrafficSegmentPanel } from './components/TrafficSegmentPanel';

type AdminView = 'map' | 'triage' | 'traffic' | 'fleet';

export default function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = window.localStorage.getItem('roadsense-admin-theme');
    return saved === 'light' ? 'light' : 'dark';
  });
  const [view, setView] = useState<AdminView>('map');
  const [streamConnected, setStreamConnected] = useState(false);

  const [segments, setSegments] = useState<RoadSegment[]>([]);
  const [events, setEvents] = useState<RoadEventRecord[]>([]);
  const [parking, setParking] = useState<ParkingSegment[]>([]);
  const [fleetData, setFleetData] = useState<FleetCompliancePayload | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<RoadEventRecord | null>(null);
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    window.localStorage.setItem('roadsense-admin-theme', theme);
  }, [theme]);

  const refreshAll = useCallback(async () => {
    const [net, evts, park, fleet] = await Promise.all([
      api.getNetwork(),
      api.listEvents(),
      api.getParking(),
      api.getFleet(),
    ]);
    setSegments(net.segments);
    setEvents(evts.events);
    setParking(park.segments);
    setFleetData(fleet);
    setSelectedEvent((prev) =>
      prev ? evts.events.find((e) => e.event_id === prev.event_id) || null : null,
    );
  }, []);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    return subscribeRoadStream(
      () => {
        void refreshAll();
      },
      (connected) => setStreamConnected(connected),
    );
  }, [refreshAll]);

  const handleModerate = useCallback(
    async (eventId: string, status: WorkflowStatus, severity?: 'low' | 'medium' | 'high') => {
      await api.moderateEvent(eventId, status, severity);
      await refreshAll();
    },
    [refreshAll],
  );

  const handleToggleClosed = useCallback(
    async (segmentId: string, closed: boolean) => {
      await api.updateSegment(segmentId, { closed });
      await refreshAll();
    },
    [refreshAll],
  );

  const handleInjectTraffic = useCallback(
    async (segmentId: string, meanSpeedKph: number, vehicleCount: number) => {
      await api.updateSegment(segmentId, { mean_speed_kph: meanSpeedKph, vehicle_count: vehicleCount });
      await refreshAll();
    },
    [refreshAll],
  );

  const handleSimulateBurst = useCallback(async () => {
    setSimulating(true);
    try {
      const res = await api.simulateBurst();
      await refreshAll();
      setSelectedEvent(res.event);
      setView('map');
    } finally {
      setSimulating(false);
    }
  }, [refreshAll]);

  const activeHazardCount = events.filter(
    (e) => e.workflow_status === 'active' || e.workflow_status === 'verified',
  ).length;
  const congestedSegmentCount = segments.filter((s) => s.traffic.is_congested).length;
  const onlineFleetCount = fleetData ? fleetData.units.filter((u) => u.status === 'online').length : 0;

  return (
    <div className="admin-shell">
      <TopCommandBar
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
        streamConnected={streamConnected}
        activeHazardCount={activeHazardCount}
        congestedSegmentCount={congestedSegmentCount}
        onlineFleetCount={onlineFleetCount}
        totalFleetCount={fleetData?.units.length || 0}
        piiViolations={fleetData?.privacy.prohibited_attributes_detected ?? 0}
        simulating={simulating}
        onSimulateBurst={handleSimulateBurst}
      />

      <div className="admin-body">
        <aside className="nav-rail">
          <button
            type="button"
            className={`rail-btn ${view === 'map' ? 'active' : ''}`}
            onClick={() => setView('map')}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Map size={16} /> City Map
            </span>
            <span className="badge tabular">{activeHazardCount}</span>
          </button>

          <button
            type="button"
            className={`rail-btn ${view === 'triage' ? 'active' : ''}`}
            onClick={() => setView('triage')}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ListFilter size={16} /> Event Triage
            </span>
            <span className="badge tabular">{events.length}</span>
          </button>

          <button
            type="button"
            className={`rail-btn ${view === 'traffic' ? 'active' : ''}`}
            onClick={() => setView('traffic')}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Activity size={16} /> Traffic &amp; Roads
            </span>
            <span className="badge tabular">{congestedSegmentCount}</span>
          </button>

          <button
            type="button"
            className={`rail-btn ${view === 'fleet' ? 'active' : ''}`}
            onClick={() => setView('fleet')}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Cpu size={16} /> Fleet &amp; Privacy
            </span>
            <span className="badge tabular">{fleetData?.units.length ?? 0}</span>
          </button>
        </aside>

        <main className="main-content">
          {view === 'map' && (
            <CityRoadHealthMap
              theme={theme}
              segments={segments}
              events={events}
              parking={parking}
              fleet={fleetData?.units || []}
              selectedEvent={selectedEvent}
              onSelectEvent={setSelectedEvent}
              onModerateEvent={handleModerate}
            />
          )}

          {view === 'triage' && (
            <EventTriageQueue
              events={events}
              onInspect={(evt) => {
                setSelectedEvent(evt);
                setView('map');
              }}
              onModerateEvent={handleModerate}
            />
          )}

          {view === 'traffic' && (
            <TrafficSegmentPanel
              segments={segments}
              onToggleClosed={handleToggleClosed}
              onInjectTraffic={handleInjectTraffic}
            />
          )}

          {view === 'fleet' && (
            <FleetSensorHealth fleetData={fleetData} parking={parking} />
          )}
        </main>
      </div>
    </div>
  );
}

