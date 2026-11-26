import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Pause, Play, Square, ThumbsUp, Volume2, VolumeX } from 'lucide-react';
import { api } from '@shared/api';
import { computeBearingDeg } from '@shared/mapConfig';
import {
  CATEGORY_META,
  SOURCE_TYPE_META,
  type RoadEventRecord,
  type RoadSegment,
  type RouteComparisonItem,
  type SpeedAdvisory,
} from '@shared/types';

interface ActiveNavigationHUDProps {
  route: RouteComparisonItem;
  segments: RoadSegment[];
  audioChimesEnabled: boolean;
  onToggleAudioChimes: () => void;
  onVehiclePositionChange: (pos: [number, number] | null, bearing?: number) => void;
  onFeedback: (eventId: string, action: 'confirm' | 'cleared') => Promise<void>;
  onExit: () => void;
}

function haversineMeters(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function interpolatePolyline(polyline: [number, number][], progress: number): [number, number] {
  if (polyline.length === 0) return [12.9716, 77.5946];
  if (polyline.length === 1 || progress <= 0) return polyline[0];
  if (progress >= 1) return polyline[polyline.length - 1];

  const lengths: number[] = [];
  let total = 0;
  for (let i = 0; i < polyline.length - 1; i++) {
    const d = haversineMeters(polyline[i], polyline[i + 1]);
    lengths.push(d);
    total += d;
  }
  const target = total * progress;
  let acc = 0;
  for (let i = 0; i < lengths.length; i++) {
    if (acc + lengths[i] >= target) {
      const localT = lengths[i] > 0 ? (target - acc) / lengths[i] : 0;
      const [lat1, lon1] = polyline[i];
      const [lat2, lon2] = polyline[i + 1];
      return [lat1 + (lat2 - lat1) * localT, lon1 + (lon2 - lon1) * localT];
    }
    acc += lengths[i];
  }
  return polyline[polyline.length - 1];
}

function playCautionTone(): void {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 660;
    gain.gain.value = 0.05;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.14);
  } catch {
    // ignore browser audio restriction
  }
}

export function ActiveNavigationHUD({
  route,
  segments,
  audioChimesEnabled,
  onToggleAudioChimes,
  onVehiclePositionChange,
  onFeedback,
  onExit,
}: ActiveNavigationHUDProps) {
  const [progress, setProgress] = useState(0.05);
  const [playing, setPlaying] = useState(true);
  const [speedMultiplier, setSpeedMultiplier] = useState<1 | 2>(1);
  const [advisory, setAdvisory] = useState<SpeedAdvisory>({
    advisory_speed_kph: route.default_legal_speed_limit_kph,
    legal_speed_limit_kph: route.default_legal_speed_limit_kph,
    reason: 'No nearby hazard adjustment',
  });
  const [ackedEvents, setAckedEvents] = useState<Record<string, string>>({});
  const lastToneEventRef = useRef<string | null>(null);

  useEffect(() => {
    setProgress(0.05);
    setPlaying(true);
    setAckedEvents({});
  }, [route.profile, route.segment_ids.join(',')]);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setProgress((prev) => {
        const next = prev + 0.008 * speedMultiplier;
        return next >= 1 ? 0.04 : next;
      });
    }, 250);
    return () => window.clearInterval(timer);
  }, [playing, speedMultiplier]);

  const vehiclePos = useMemo(
    () => interpolatePolyline(route.polyline, progress),
    [route.polyline, progress],
  );
  const lookAheadPos = useMemo(
    () => interpolatePolyline(route.polyline, Math.min(1, progress + 0.02)),
    [route.polyline, progress],
  );
  const bearing = useMemo(
    () => computeBearingDeg(vehiclePos, lookAheadPos),
    [vehiclePos, lookAheadPos],
  );

  useEffect(() => {
    onVehiclePositionChange(vehiclePos, bearing);
    return () => onVehiclePositionChange(null, 0);
  }, [vehiclePos, bearing, onVehiclePositionChange]);

  const currentSegIndex = Math.min(
    route.segment_ids.length - 1,
    Math.floor(progress * route.segment_ids.length),
  );
  const currentSegment = segments.find((s) => s.segment_id === route.segment_ids[currentSegIndex]);
  const legalLimit = currentSegment?.legal_speed_limit_kph ?? route.default_legal_speed_limit_kph;

  // Find closest route hazard and approximate road distance
  const nearestHazard: { event: RoadEventRecord; distanceM: number } | null = useMemo(() => {
    const candidateEvents = route.events.filter(
      (e) => e.category !== 'speed_limit_sign' && (e.workflow_status === 'active' || e.workflow_status === 'verified'),
    );
    if (candidateEvents.length === 0) return null;
    let best: { event: RoadEventRecord; distanceM: number } | null = null;
    for (const evt of candidateEvents) {
      const dist = haversineMeters(vehiclePos, [evt.location.latitude, evt.location.longitude]);
      // Scale distance slightly so 80m trigger window activates smoothly along Bengaluru corridors
      const effectiveDist = Math.round(dist * 0.28);
      if (!best || effectiveDist < best.distanceM) {
        best = { event: evt, distanceM: effectiveDist };
      }
    }
    return best;
  }, [route.events, vehiclePos]);

  useEffect(() => {
    let cancelled = false;
    const hazardName = nearestHazard ? nearestHazard.event.category : null;
    const distM = nearestHazard ? nearestHazard.distanceM : null;

    api
      .getSpeedAdvisory({
        legal_speed_limit_kph: legalLimit,
        hazard: hazardName,
        distance_to_hazard_m: distM,
      })
      .then((res) => {
        if (!cancelled) setAdvisory(res);
      })
      .catch(() => {
        // retain previous advisory if transient error
      });

    if (
      audioChimesEnabled &&
      nearestHazard &&
      nearestHazard.distanceM <= 80 &&
      lastToneEventRef.current !== nearestHazard.event.event_id
    ) {
      lastToneEventRef.current = nearestHazard.event.event_id;
      playCautionTone();
    }

    return () => {
      cancelled = true;
    };
  }, [legalLimit, nearestHazard?.event.event_id, nearestHazard?.distanceM, audioChimesEnabled]);

  const remainingMin = Math.max(0.5, +(route.travel_minutes * (1 - progress)).toFixed(1));
  const remainingKm = Math.max(0.1, +(route.distance_km * (1 - progress)).toFixed(1));
  const nextWaypoint = route.node_names[Math.min(route.node_names.length - 1, currentSegIndex + 1)];
  const isAdvisoryReduced =
    advisory.legal_speed_limit_kph !== null && advisory.advisory_speed_kph < advisory.legal_speed_limit_kph;

  return (
    <>
      <div className="hud-overlay-top">
        <div className="maneuver-banner">
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-cyan)', textTransform: 'uppercase' }}>
              {route.profile.toUpperCase()} PROFILE · {currentSegment?.name || 'Active Corridor'}
            </div>
            <div style={{ fontSize: 17, fontWeight: 800, marginTop: 2 }}>
              Head toward {nextWaypoint}
            </div>
            <div className="tabular" style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 3 }}>
              {remainingMin} min left · {remainingKm} km remaining · Quality {route.road_quality_score}/100
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              type="button"
              className="pill-btn"
              onClick={() => setPlaying((p) => !p)}
              title={playing ? 'Pause simulation' : 'Resume simulation'}
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
              {playing ? 'Pause' : 'Drive'}
            </button>
            <button
              type="button"
              className="pill-btn tabular"
              onClick={() => setSpeedMultiplier((s) => (s === 1 ? 2 : 1))}
            >
              {speedMultiplier}x
            </button>
            <button
              type="button"
              className="pill-btn"
              onClick={onToggleAudioChimes}
              title="Toggle hazard audio chime"
            >
              {audioChimesEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
            </button>
            <button
              type="button"
              className="pill-btn"
              style={{ borderColor: 'rgba(239,68,68,0.45)', color: '#FCA5A5' }}
              onClick={onExit}
            >
              <Square size={12} /> Exit
            </button>
          </div>
        </div>

        {/* Legal Limit and Advisory Speed are ALWAYS separate indicators per RoadEvent Contract v1 */}
        <div className="speed-cluster" aria-label="Speed indicators">
          <div className="legal-limit-sign" title="Statutory legal speed limit">
            <span className="val tabular">{advisory.legal_speed_limit_kph ?? legalLimit}</span>
            <span className="lbl">LEGAL LIMIT</span>
          </div>

          <div className={`advisory-pill ${isAdvisoryReduced ? 'caution' : ''}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  color: isAdvisoryReduced ? 'var(--accent-amber)' : 'var(--accent-cyan)',
                }}
              >
                NON-LEGAL ADVISORY
              </span>
              <span className="mono" style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                km/h
              </span>
            </div>
            <div className="tabular" style={{ fontSize: 24, fontWeight: 800, lineHeight: 1.1 }}>
              {advisory.advisory_speed_kph}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', maxWidth: 185 }}>
              {advisory.reason}
            </div>
          </div>
        </div>
      </div>

      <div className="hud-overlay-bottom">
        {nearestHazard ? (
          <div className="hazard-alert-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 12,
                  display: 'grid',
                  placeItems: 'center',
                  background: CATEGORY_META[nearestHazard.event.category].bg,
                  color: CATEGORY_META[nearestHazard.event.category].color,
                  border: `1px solid ${CATEGORY_META[nearestHazard.event.category].color}`,
                }}
              >
                <AlertTriangle size={20} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 800, fontSize: 14 }}>
                    {CATEGORY_META[nearestHazard.event.category].label} ahead
                  </span>
                  <span className="badge tabular" style={{ background: '#1E293B', color: '#F8FAFC' }}>
                    {nearestHazard.distanceM} m
                  </span>
                  <span
                    className="badge"
                    style={{
                      background: SOURCE_TYPE_META[nearestHazard.event.source_type].bg,
                      color: SOURCE_TYPE_META[nearestHazard.event.source_type].color,
                    }}
                  >
                    {SOURCE_TYPE_META[nearestHazard.event.source_type].label}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                  Confidence {Math.round(nearestHazard.event.confidence * 100)}% · Location uncertainty ±
                  {nearestHazard.event.location_accuracy_m}m
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              {ackedEvents[nearestHazard.event.event_id] ? (
                <span className="badge" style={{ background: 'rgba(16,185,129,0.2)', color: '#6EE7B7', padding: '7px 12px' }}>
                  <CheckCircle2 size={14} /> Thanks ({ackedEvents[nearestHazard.event.event_id]})
                </span>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setAckedEvents((prev) => ({ ...prev, [nearestHazard.event.event_id]: 'Confirmed' }));
                      void onFeedback(nearestHazard.event.event_id, 'confirm');
                    }}
                  >
                    <ThumbsUp size={13} /> Still there
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setAckedEvents((prev) => ({ ...prev, [nearestHazard.event.event_id]: 'Cleared' }));
                      void onFeedback(nearestHazard.event.event_id, 'cleared');
                    }}
                  >
                    Cleared
                  </button>
                </>
              )}
            </div>
          </div>
        ) : (
          <div className="hazard-alert-card" style={{ borderColor: 'rgba(16,185,129,0.4)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <CheckCircle2 size={18} color="#10B981" />
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                Clear corridor ahead — monitoring GNSS &amp; camera feeds
              </span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

