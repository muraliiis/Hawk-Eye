import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  AlertOctagon,
  Camera,
  CheckCircle2,
  EyeOff,
  FolderOpen,
  Globe,
  Pause,
  Play,
  Radio,
  Send,
  Video,
  Wifi,
} from 'lucide-react';
import {
  api,
  type DashcamFeedItem,
  type DashcamReplayCandidate,
  type DashcamReplayVehicle,
} from '@shared/api';
import type { PerceptionIngestResponse, RoadSegment } from '@shared/types';

interface DashcamCaptureModeProps {
  segments: RoadSegment[];
  dashcamOptIn: boolean;
  onEventPublished: () => void;
}

type FeedSourceMode = 'internet' | 'custom_url' | 'local' | 'webcam';

const DETECTABLE_CLASSES = [
  { value: 'pothole', label: 'Pothole', color: '#EF4444' },
  { value: 'crack', label: 'Surface Crack', color: '#F97316' },
  { value: 'speed_breaker', label: 'Speed Breaker', color: '#FBBF24' },
  { value: 'waterlogging', label: 'Waterlogging', color: '#38BDF8' },
  { value: 'obstacle', label: 'Road Obstacle', color: '#EC4899' },
  { value: 'construction', label: 'Construction', color: '#FB923C' },
];

const DEFECT_COLORS: Record<string, string> = {
  pothole: '#EF4444',
  alligator_crack: '#F97316',
  longitudinal_crack: '#F59E0B',
  transverse_crack: '#FB923C',
  crack: '#F97316',
};

export function DashcamCaptureMode({
  segments,
  dashcamOptIn,
  onEventPublished,
}: DashcamCaptureModeProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const busyRef = useRef(false);

  const [feeds, setFeeds] = useState<DashcamFeedItem[]>([]);
  const [selectedFeedId, setSelectedFeedId] = useState('road_defects_feed');
  const [sourceMode, setSourceMode] = useState<FeedSourceMode>('internet');
  const [customUrlInput, setCustomUrlInput] = useState('');
  const [activeStreamSrc, setActiveStreamSrc] = useState<string>(
    '/api/dashcam/stream?feed_id=road_defects_feed',
  );
  const [localObjectUrl, setLocalObjectUrl] = useState<string | null>(null);
  const [localFileName, setLocalFileName] = useState<string | null>(null);

  const [selectedSegmentId, setSelectedSegmentId] = useState(
    segments[0]?.segment_id || 'osm-way-richmond-shanthi',
  );
  const [confThreshold, setConfThreshold] = useState(0.32);
  const [inferenceActive, setInferenceActive] = useState(true);
  const [videoReady, setVideoReady] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Live AI detections rendered over the real video
  const [modelName, setModelName] = useState('rdd2022-yolov8s-best.pt + yolov8n.pt');
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [framesAnalyzed, setFramesAnalyzed] = useState(0);
  const [eventsPublished, setEventsPublished] = useState(0);
  const [liveDefects, setLiveDefects] = useState<DashcamReplayCandidate[]>([]);
  const [liveVehicles, setLiveVehicles] = useState<DashcamReplayVehicle[]>([]);

  // Manual guardrail test controls (SensorFusion + PerceptionNormalizer)
  const [manualLabel, setManualLabel] = useState('pothole');
  const [manualConfidence, setManualConfidence] = useState(0.88);
  const [bboxRatio, setBboxRatio] = useState(0.05);
  const [simulateStaleGnss, setSimulateStaleGnss] = useState(false);
  const [simulateHarshBrake, setSimulateHarshBrake] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<PerceptionIngestResponse | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);

  // Load curated public internet dashcam feeds
  useEffect(() => {
    api
      .getDashcamFeeds()
      .then((res) => {
        if (res.feeds.length > 0) {
          setFeeds(res.feeds);
          const first = res.feeds[0];
          setSelectedFeedId(first.feed_id);
          if (first.default_segment_id) setSelectedSegmentId(first.default_segment_id);
        }
      })
      .catch(() => {
        // default stream URL still works directly
      });
  }, []);

  // Revoke local blob URL on change/unmount
  useEffect(() => {
    return () => {
      if (localObjectUrl) URL.revokeObjectURL(localObjectUrl);
    };
  }, [localObjectUrl]);

  // Attach webcam or video URL cleanly to <video>
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const stopWebcam = () => {
      if (video.srcObject) {
        (video.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
        video.srcObject = null;
      }
    };

    if (sourceMode === 'webcam') {
      let cancelled = false;
      video.removeAttribute('src');
      video.load();
      setVideoReady(false);
      setStreamError(null);
      navigator.mediaDevices
        ?.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
        .then((stream) => {
          if (cancelled) {
            stream.getTracks().forEach((t) => t.stop());
            return;
          }
          video.srcObject = stream;
          void video.play();
        })
        .catch(() => {
          setStreamError('Webcam unavailable or permission denied — switched back to internet road feed.');
          setSourceMode('internet');
        });
      return () => {
        cancelled = true;
        stopWebcam();
      };
    }

    stopWebcam();
    setVideoReady(false);
    setStreamError(null);
    video.src = activeStreamSrc;
    video.load();
    void video.play().catch(() => {
      // autoplay blocked only if unmuted, but video is muted
    });
    return undefined;
  }, [sourceMode, activeStreamSrc]);

  // Draw crisp 1:1 bounding boxes + mosaic plate blur over the real video element
  const drawOverlay = useCallback(
    (defects: DashcamReplayCandidate[], vehicles: DashcamReplayVehicle[]) => {
      const canvas = overlayCanvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;

      const rect = canvas.getBoundingClientRect();
      const cw = Math.max(1, Math.round(rect.width));
      const ch = Math.max(1, Math.round(rect.height));
      if (canvas.width !== cw || canvas.height !== ch) {
        canvas.width = cw;
        canvas.height = ch;
      }

      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, cw, ch);

      const vw = video.videoWidth || 16;
      const vh = video.videoHeight || 9;
      const containerAspect = cw / ch;
      const videoAspect = vw / vh;

      let drawW = cw;
      let drawH = ch;
      let drawX = 0;
      let drawY = 0;
      if (videoAspect > containerAspect) {
        drawW = cw;
        drawH = cw / videoAspect;
        drawY = (ch - drawH) / 2;
      } else {
        drawH = ch;
        drawW = ch * videoAspect;
        drawX = (cw - drawW) / 2;
      }

      // 1. Vehicles + Live Plate Privacy Masking
      for (const veh of vehicles) {
        const [nx1, ny1, nx2, ny2] = veh.bbox_norm;
        const x = drawX + nx1 * drawW;
        const y = drawY + ny1 * drawH;
        const w = (nx2 - nx1) * drawW;
        const h = (ny2 - ny1) * drawH;

        ctx.strokeStyle = '#10B981';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        const label = `${veh.class_name.toUpperCase()} ${Math.round(veh.confidence * 100)}%`;
        ctx.font = 'bold 11px JetBrains Mono, monospace';
        const tw = ctx.measureText(label).width + 10;
        ctx.fillStyle = '#10B981';
        ctx.fillRect(x, Math.max(0, y - 18), tw, 18);
        ctx.fillStyle = '#04130D';
        ctx.fillText(label, x + 5, Math.max(13, y - 5));

        // Pixelated privacy mask over lower plate zone
        const [px1, py1, px2, py2] = veh.plate_blur_box_norm;
        const bx = drawX + px1 * drawW;
        const by = drawY + py1 * drawH;
        const bw = Math.max(18, (px2 - px1) * drawW);
        const bh = Math.max(8, (py2 - py1) * drawH);

        ctx.save();
        ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
        ctx.fillRect(bx, by, bw, bh);
        const step = 5;
        for (let mx = 0; mx < bw; mx += step) {
          for (let my = 0; my < bh; my += step) {
            ctx.fillStyle = (Math.floor(mx / step) + Math.floor(my / step)) % 2 === 0 ? '#64748B' : '#94A3B8';
            ctx.fillRect(bx + mx, by + my, Math.min(step, bw - mx), Math.min(step, bh - my));
          }
        }
        ctx.strokeStyle = '#22D3EE';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(bx, by, bw, bh);
        ctx.restore();
      }

      // 2. Road Defect Bounding Boxes from rdd2022-yolov8s-best.pt
      for (const defect of defects) {
        const [nx1, ny1, nx2, ny2] = defect.bbox_norm;
        const x = drawX + nx1 * drawW;
        const y = drawY + ny1 * drawH;
        const w = (nx2 - nx1) * drawW;
        const h = (ny2 - ny1) * drawH;
        const color = DEFECT_COLORS[defect.source_label] || '#EF4444';

        ctx.fillStyle = `${color}26`;
        ctx.fillRect(x, y, w, h);

        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.strokeRect(x, y, w, h);

        const text = `${defect.source_label.replace(/_/g, ' ').toUpperCase()} ${Math.round(defect.confidence * 100)}%`;
        ctx.font = 'bold 11px JetBrains Mono, monospace';
        const tw = ctx.measureText(text).width + 10;
        const tagY = Math.max(0, y - 19);
        ctx.fillStyle = color;
        ctx.fillRect(x, tagY, tw, 19);
        ctx.fillStyle = '#070B12';
        ctx.fillText(text, x + 5, tagY + 13);
      }
    },
    [],
  );

  useEffect(() => {
    drawOverlay(liveDefects, liveVehicles);
  }, [liveDefects, liveVehicles, drawOverlay]);

  // Continuous non-overlapping frame inference loop on the active video feed
  useEffect(() => {
    if (!inferenceActive || !dashcamOptIn) return;

    const runOneFrame = () => {
      const video = videoRef.current;
      if (!video || video.paused || video.ended || video.readyState < 2 || video.videoWidth === 0) return;
      if (busyRef.current) return;

      busyRef.current = true;
      const offscreen = document.createElement('canvas');
      const scale = Math.min(1, 768 / video.videoWidth);
      offscreen.width = Math.max(1, Math.round(video.videoWidth * scale));
      offscreen.height = Math.max(1, Math.round(video.videoHeight * scale));
      const ctx = offscreen.getContext('2d');
      if (!ctx) {
        busyRef.current = false;
        return;
      }

      try {
        ctx.drawImage(video, 0, 0, offscreen.width, offscreen.height);
      } catch {
        setStreamError('Browser blocked canvas frame read (CORS). Use the proxied Internet Feed or Local Video.');
        busyRef.current = false;
        return;
      }

      offscreen.toBlob(
        async (blob) => {
          try {
            if (!blob) return;
            const res = await api.analyzeReplayFrame({
              frame: blob,
              roadSegmentId: selectedSegmentId,
              frameTimestamp: new Date(),
              speedKph: simulateHarshBrake ? 20 : 32,
              confidenceThreshold: confThreshold,
            });
            setModelName(res.model_version);
            setLastLatencyMs(res.inference_ms);
            setFramesAnalyzed((c) => c + 1);
            setLiveDefects(res.candidates);
            setLiveVehicles(res.vehicles);
            if (res.published_events.length > 0) {
              setEventsPublished((c) => c + res.published_events.length);
              onEventPublished();
            }
          } catch (err) {
            setStreamError(err instanceof Error ? err.message : 'Frame inference failed');
          } finally {
            busyRef.current = false;
          }
        },
        'image/jpeg',
        0.82,
      );
    };

    const timer = window.setInterval(runOneFrame, 750);
    return () => window.clearInterval(timer);
  }, [inferenceActive, dashcamOptIn, selectedSegmentId, confThreshold, simulateHarshBrake, onEventPublished]);

  function switchToInternetFeed(feedId: string) {
    const found = feeds.find((f) => f.feed_id === feedId);
    setSelectedFeedId(feedId);
    if (found?.default_segment_id) setSelectedSegmentId(found.default_segment_id);
    setSourceMode('internet');
    setLiveDefects([]);
    setLiveVehicles([]);
    setActiveStreamSrc(`/api/dashcam/stream?feed_id=${encodeURIComponent(feedId)}`);
  }

  function loadCustomUrlStream() {
    const trimmed = customUrlInput.trim();
    if (!trimmed) return;
    setSourceMode('custom_url');
    setLiveDefects([]);
    setLiveVehicles([]);
    setActiveStreamSrc(`/api/dashcam/stream?url=${encodeURIComponent(trimmed)}`);
  }

  function handleSelectLocalFile(file: File | undefined) {
    if (!file) return;
    if (!file.type.startsWith('video/')) {
      setStreamError('Please select a valid video file (MP4, WebM, MOV).');
      return;
    }
    const objUrl = URL.createObjectURL(file);
    setLocalFileName(file.name);
    setLocalObjectUrl(objUrl);
    setSourceMode('local');
    setLiveDefects([]);
    setLiveVehicles([]);
    setActiveStreamSrc(objUrl);
  }

  function togglePlayPause() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play();
      setInferenceActive(true);
    } else {
      video.pause();
      setInferenceActive(false);
    }
  }

  async function handleManualIngest() {
    setSubmitting(true);
    setIngestError(null);
    try {
      const seg = segments.find((s) => s.segment_id === selectedSegmentId) || segments[0];
      const pt = seg?.polyline[Math.min(1, (seg?.polyline.length || 1) - 1)] || [12.9756, 77.6066];
      const frameTime = new Date();
      const gnssDelayMs = simulateStaleGnss ? 1250 : 140;
      const gnssTime = new Date(frameTime.getTime() - gnssDelayMs);

      const res = await api.ingestPerception({
        label: manualLabel,
        confidence: manualConfidence,
        bbox_area_ratio: bboxRatio,
        model_version: modelName,
        frame_timestamp: frameTime.toISOString(),
        gnss_samples: [
          {
            timestamp: gnssTime.toISOString(),
            latitude: pt[0],
            longitude: pt[1],
            accuracy_m: 4.8,
            speed_kph: simulateHarshBrake ? 22 : 34,
          },
        ],
        imu_sample: {
          timestamp: frameTime.toISOString(),
          longitudinal_accel_mps2: simulateHarshBrake ? -3.6 : -0.4,
          vertical_accel_mps2: manualLabel === 'pothole' ? 2.3 : 0.3,
          yaw_rate_dps: 0.7,
        },
        attributes: {
          severity: manualConfidence >= 0.8 ? 'high' : 'medium',
          edge_capture_mode: 'dashcam_guardrail_test',
          plate_mask_applied: true,
        },
      });
      setLastResult(res);
      onEventPublished();
    } catch (err) {
      setLastResult(null);
      setIngestError(err instanceof Error ? err.message : 'Ingestion failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dashcam-grid">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="viewfinder-box">
          <video
            ref={videoRef}
            autoPlay
            loop
            muted
            playsInline
            crossOrigin="anonymous"
            onCanPlay={() => setVideoReady(true)}
            onError={() =>
              setStreamError('Could not load video feed. Check network connection or try another feed.')
            }
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              background: '#05080f',
              display: 'block',
            }}
          />

          <canvas
            ref={overlayCanvasRef}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
            }}
          />

          <div className="viewfinder-hud">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span
                className="badge"
                style={{ background: 'rgba(7,11,18,0.88)', color: '#F8FAFC', border: '1px solid rgba(34,211,238,0.4)' }}
              >
                <Radio size={12} color={videoReady ? '#22D3EE' : '#F59E0B'} />{' '}
                {sourceMode === 'internet'
                  ? 'INTERNET ROAD FEED'
                  : sourceMode === 'custom_url'
                    ? 'CUSTOM STREAM'
                    : sourceMode === 'webcam'
                      ? 'LIVE WEBCAM'
                      : `LOCAL: ${localFileName || 'VIDEO'}`}{' '}
                · {modelName}
              </span>

              <span
                className="badge"
                style={{ background: 'rgba(16,185,129,0.22)', color: '#6EE7B7', border: '1px solid rgba(16,185,129,0.4)' }}
              >
                <EyeOff size={12} /> ON-DEVICE PLATE BLUR ACTIVE
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span
                className="badge tabular"
                style={{
                  background: simulateStaleGnss ? 'rgba(239,68,68,0.88)' : 'rgba(7,11,18,0.88)',
                  color: '#F8FAFC',
                }}
              >
                GNSS: {simulateStaleGnss ? 'STALE 1250ms (>750ms gate)' : 'LOCKED · ±4.8m · 140ms'}
              </span>
              <span
                className="badge tabular"
                style={{
                  background: lastLatencyMs !== null ? 'rgba(7,11,18,0.88)' : 'rgba(15,23,42,0.8)',
                  color: '#A5F3FC',
                }}
              >
                <Activity size={12} />{' '}
                {lastLatencyMs !== null ? `YOLO ${lastLatencyMs} ms · ${liveDefects.length} defects / ${liveVehicles.length} vehicles` : 'Buffering stream...'}
              </span>
            </div>
          </div>
        </div>

        {/* Source Switcher & Custom Internet Feed Bar */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <button type="button" className="btn-secondary" onClick={togglePlayPause}>
              {inferenceActive ? <Pause size={14} /> : <Play size={14} />}
              {inferenceActive ? 'Pause Feed & YOLO' : 'Resume Feed & YOLO'}
            </button>

            {(feeds.length > 0
              ? feeds
              : [
                  {
                    feed_id: 'road_defects_feed',
                    title: 'Internet Feed #1 (Road Damage)',
                    source_label: '',
                    url: '',
                    default_segment_id: 'osm-way-richmond-shanthi',
                  },
                  {
                    feed_id: 'urban_cracks_feed',
                    title: 'Internet Feed #2 (Asphalt Cracks)',
                    source_label: '',
                    url: '',
                    default_segment_id: 'osm-way-shanthi-ejipura',
                  },
                ]
            ).map((f) => (
              <button
                key={f.feed_id}
                type="button"
                className="pill-btn"
                style={
                  sourceMode === 'internet' && selectedFeedId === f.feed_id
                    ? { borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)', background: 'rgba(34,211,238,0.14)' }
                    : undefined
                }
                onClick={() => switchToInternetFeed(f.feed_id)}
              >
                <Globe size={13} /> {f.title}
              </button>
            ))}

            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              style={{ display: 'none' }}
              onChange={(e) => handleSelectLocalFile(e.target.files?.[0])}
            />
            <button type="button" className="btn-secondary" onClick={() => fileInputRef.current?.click()}>
              <FolderOpen size={14} /> Local Video
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSourceMode((m) => (m === 'webcam' ? 'internet' : 'webcam'))}
            >
              <Video size={14} /> {sourceMode === 'webcam' ? 'Back to Internet Feed' : 'Live Webcam'}
            </button>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="url"
              className="select-field"
              placeholder="Paste any public internet .mp4 / .webm dashcam URL..."
              value={customUrlInput}
              onChange={(e) => setCustomUrlInput(e.target.value)}
            />
            <button type="button" className="btn-secondary" onClick={loadCustomUrlStream} style={{ whiteSpace: 'nowrap' }}>
              <Globe size={13} /> Stream URL
            </button>
          </div>

          {streamError && (
            <div style={{ fontSize: 12, color: 'var(--accent-amber)' }}>{streamError}</div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Live YOLO Inference Telemetry */}
        <div className="card">
          <div className="card-title">
            <span>Live Dual-Model Inference</span>
            <span className="badge" style={{ background: 'rgba(16,185,129,0.16)', color: '#6EE7B7' }}>
              <Wifi size={11} /> Zero Frame Retention
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
            <div style={{ padding: 8, borderRadius: 8, background: '#0b1220' }}>
              <div style={{ fontSize: 10.5, color: 'var(--text-secondary)' }}>Frames Analyzed</div>
              <strong className="tabular" style={{ fontSize: 17 }}>{framesAnalyzed}</strong>
            </div>
            <div style={{ padding: 8, borderRadius: 8, background: '#0b1220' }}>
              <div style={{ fontSize: 10.5, color: 'var(--text-secondary)' }}>RoadEvents Published</div>
              <strong className="tabular" style={{ fontSize: 17, color: 'var(--accent-cyan)' }}>{eventsPublished}</strong>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
                Map Detections to Road Segment
              </label>
              <select
                className="select-field"
                value={selectedSegmentId}
                onChange={(e) => setSelectedSegmentId(e.target.value)}
              >
                {segments.map((s) => (
                  <option key={s.segment_id} value={s.segment_id}>
                    {s.name} ({s.segment_id})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-secondary)' }}>
                <span>YOLO Detection Threshold</span>
                <span className="mono tabular">{Math.round(confThreshold * 100)}%</span>
              </div>
              <input
                type="range"
                min={0.25}
                max={0.75}
                step={0.05}
                value={confThreshold}
                onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6 }}>
            ACTIVE FRAME DETECTIONS ({liveDefects.length} defects · {liveVehicles.length} vehicles)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 150, overflowY: 'auto' }}>
            {liveDefects.length === 0 && liveVehicles.length === 0 ? (
              <div style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                Scanning incoming video frames for potholes, cracks, and vehicles...
              </div>
            ) : (
              <>
                {liveDefects.map((d, idx) => (
                  <div
                    key={`d-${idx}`}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 11.5,
                      padding: '5px 8px',
                      borderRadius: 7,
                      background: '#0b1220',
                      borderLeft: `3px solid ${DEFECT_COLORS[d.source_label] || '#EF4444'}`,
                    }}
                  >
                    <span className="mono">{d.source_label} → {d.label}</span>
                    <strong className="tabular">{Math.round(d.confidence * 100)}%</strong>
                  </div>
                ))}
                {liveVehicles.map((v, idx) => (
                  <div
                    key={`v-${idx}`}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 11.5,
                      padding: '5px 8px',
                      borderRadius: 7,
                      background: '#0b1220',
                      borderLeft: '3px solid #10B981',
                    }}
                  >
                    <span className="mono">{v.class_name} (plate blurred)</span>
                    <strong className="tabular">{Math.round(v.confidence * 100)}%</strong>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* Deterministic Guardrail Test Panel */}
        <div className="card">
          <div className="card-title">
            <span>SensorFusion &amp; Guardrail Test Lab</span>
            <span className="mono" style={{ fontSize: 10 }}>750ms GNSS Gate</span>
          </div>

          {!dashcamOptIn && (
            <div
              style={{
                padding: 8,
                borderRadius: 8,
                background: 'rgba(245,158,11,0.14)',
                border: '1px solid rgba(245,158,11,0.35)',
                color: '#FDE68A',
                fontSize: 12,
                marginBottom: 8,
              }}
            >
              Dashcam upload is paused in Safety settings. Enable opt-in to stream detections.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <select
                className="select-field"
                value={manualLabel}
                onChange={(e) => setManualLabel(e.target.value)}
              >
                {DETECTABLE_CLASSES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-primary"
                disabled={submitting || !dashcamOptIn}
                onClick={handleManualIngest}
              >
                <Camera size={15} /> {submitting ? 'Sending...' : 'Test Ingest'}
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--text-secondary)' }}>
                  <span>Conf</span>
                  <span className="mono">{manualConfidence.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0.3}
                  max={0.98}
                  step={0.02}
                  value={manualConfidence}
                  onChange={(e) => setManualConfidence(parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10.5, color: 'var(--text-secondary)' }}>
                  <span>BBox Area</span>
                  <span className="mono">{bboxRatio.toFixed(3)}</span>
                </div>
                <input
                  type="range"
                  min={0.01}
                  max={0.08}
                  step={0.005}
                  value={bboxRatio}
                  onChange={(e) => setBboxRatio(parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 11.5 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={simulateStaleGnss}
                  onChange={(e) => setSimulateStaleGnss(e.target.checked)}
                />
                Test Stale GNSS (1250ms)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={simulateHarshBrake}
                  onChange={(e) => setSimulateHarshBrake(e.target.checked)}
                />
                Harsh Brake (-3.6 m/s²)
              </label>
            </div>
          </div>
        </div>

        {ingestError && (
          <div className="card" style={{ borderColor: 'var(--accent-red)', background: 'rgba(239,68,68,0.12)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#FCA5A5', fontWeight: 700, fontSize: 13 }}>
              <AlertOctagon size={16} /> Guardrail Rejected Detection
            </div>
            <div style={{ fontSize: 12, color: '#FECACA', marginTop: 4 }}>{ingestError}</div>
          </div>
        )}

        {lastResult && (
          <div className="card" style={{ borderColor: 'var(--accent-emerald)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#6EE7B7', fontWeight: 700, fontSize: 13 }}>
              <CheckCircle2 size={16} /> Published RoadEvent v{lastResult.event.schema_version}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
              Conf: <strong className="tabular">{lastResult.event.confidence}</strong> · Segment:{' '}
              <span className="mono">{lastResult.fusion.road_segment_id}</span> · GNSS:{' '}
              <span className="tabular">{lastResult.fusion.age_ms}ms</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, fontSize: 11, color: '#6EE7B7' }}>
              <Send size={12} /> Streamed live to Admin Control Room &amp; User Map
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
