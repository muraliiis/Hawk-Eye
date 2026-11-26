import { useState } from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { format, subDays } from 'date-fns';
import {
  AlertTriangle,
  Car,
  ParkingSquare,
  Star,
  TrendingUp,
  Map as MapIcon,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { MapContainer, TileLayer } from 'react-leaflet';
import { RoadEventType, SeverityLevel } from '@/types';
import type { RoadEvent } from '@/types';

// ─── Mock data generators ─────────────────────────────────────────────────────

function generateEventsTimeline() {
  return Array.from({ length: 7 }, (_, i) => ({
    date: format(subDays(new Date(), 6 - i), 'dd MMM'),
    potholes:     Math.floor(Math.random() * 40 + 10),
    construction: Math.floor(Math.random() * 15 + 2),
    waterlogging: Math.floor(Math.random() * 20 + 5),
    obstacles:    Math.floor(Math.random() * 10 + 1),
  }));
}

function generateEventsByType() {
  return [
    { type: 'Pothole',      count: 148 },
    { type: 'Road Damage',  count: 62 },
    { type: 'Construction', count: 34 },
    { type: 'Waterlogging', count: 55 },
    { type: 'Obstacle',     count: 23 },
    { type: 'Speed Breaker',count: 41 },
  ];
}

function generateSeverityDist() {
  return [
    { name: SeverityLevel.LOW,      value: 112, color: '#22c55e' },
    { name: SeverityLevel.MEDIUM,   value: 98,  color: '#eab308' },
    { name: SeverityLevel.HIGH,     value: 54,  color: '#f97316' },
    { name: SeverityLevel.CRITICAL, value: 19,  color: '#ef4444' },
  ];
}

const MOCK_RECENT_EVENTS: RoadEvent[] = [
  {
    id: 'e001', event_type: RoadEventType.POTHOLE, severity: SeverityLevel.HIGH,
    confidence: 0.91, location: { lat: 28.6139, lon: 77.2090 },
    reported_at: subDays(new Date(), 0).toISOString(), description: 'Large pothole on NH-48',
  },
  {
    id: 'e002', event_type: RoadEventType.WATERLOGGING, severity: SeverityLevel.CRITICAL,
    confidence: 0.87, location: { lat: 19.0760, lon: 72.8777 },
    reported_at: subDays(new Date(), 0).toISOString(), description: 'Severe waterlogging post-rain',
  },
  {
    id: 'e003', event_type: RoadEventType.CONSTRUCTION, severity: SeverityLevel.MEDIUM,
    confidence: 0.95, location: { lat: 12.9716, lon: 77.5946 },
    reported_at: subDays(new Date(), 1).toISOString(), description: 'Metro construction lane closure',
  },
  {
    id: 'e004', event_type: RoadEventType.ROAD_DAMAGE, severity: SeverityLevel.HIGH,
    confidence: 0.78, location: { lat: 17.3850, lon: 78.4867 },
    reported_at: subDays(new Date(), 1).toISOString(), description: 'Edge break near flyover',
  },
  {
    id: 'e005', event_type: RoadEventType.OBSTACLE, severity: SeverityLevel.LOW,
    confidence: 0.65, location: { lat: 13.0827, lon: 80.2707 },
    reported_at: subDays(new Date(), 2).toISOString(), description: 'Fallen tree branch cleared',
  },
  {
    id: 'e006', event_type: RoadEventType.POTHOLE, severity: SeverityLevel.MEDIUM,
    confidence: 0.82, location: { lat: 22.5726, lon: 88.3639 },
    reported_at: subDays(new Date(), 2).toISOString(), description: 'Multiple potholes, 200m stretch',
  },
];

// ─── Severity badge ───────────────────────────────────────────────────────────

function SeverityBadge({ sev }: { sev: SeverityLevel }) {
  const styles: Record<SeverityLevel, string> = {
    [SeverityLevel.CRITICAL]: 'bg-red-900 text-red-300',
    [SeverityLevel.HIGH]:     'bg-orange-900 text-orange-300',
    [SeverityLevel.MEDIUM]:   'bg-yellow-900 text-yellow-300',
    [SeverityLevel.LOW]:      'bg-green-900 text-green-300',
  };
  return (
    <span className={clsx('px-2 py-0.5 rounded text-xs font-medium', styles[sev])}>
      {sev}
    </span>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub?: string;
  trend?: 'up' | 'down' | 'neutral';
}

function StatCard({ icon, label, value, sub, trend }: StatCardProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-start gap-4">
      <div className="p-2.5 bg-gray-800 rounded-lg text-blue-400">{icon}</div>
      <div>
        <div className="text-2xl font-bold text-white tabular-nums">{value}</div>
        <div className="text-sm text-gray-400 mt-0.5">{label}</div>
        {sub && (
          <div className={clsx(
            'text-xs mt-1 flex items-center gap-1',
            trend === 'up' ? 'text-red-400' : trend === 'down' ? 'text-green-400' : 'text-gray-500'
          )}>
            {trend === 'up' && <TrendingUp className="w-3 h-3" />}
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TIMELINE_DATA   = generateEventsTimeline();
const BY_TYPE_DATA    = generateEventsByType();
const SEVERITY_DATA   = generateSeverityDist();

const CHART_COLORS = ['#3b82f6', '#f97316', '#22c55e', '#a855f7'];

export default function DashboardPage() {
  const [showMap, setShowMap] = useState(false);

  return (
    <div className="h-full overflow-y-auto bg-gray-950 text-white">
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">

        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Road Intelligence Dashboard</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Fleet & infrastructure analytics · {format(new Date(), 'EEEE, dd MMMM yyyy')}
            </p>
          </div>
          <button
            onClick={() => setShowMap((v) => !v)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors',
              showMap
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'
            )}
          >
            <MapIcon className="w-4 h-4" />
            {showMap ? 'Hide Map' : 'Show Map'}
          </button>
        </div>

        {/* ── Map View (toggle) ────────────────────────────────────────────── */}
        {showMap && (
          <div className="relative bg-gray-900 border border-gray-800 rounded-xl overflow-hidden" style={{ height: 320 }}>
            <button
              onClick={() => setShowMap(false)}
              className="absolute top-3 right-3 z-[1000] bg-gray-900 border border-gray-700 rounded-full p-1.5 text-gray-400 hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
            <MapContainer
              center={[20.5937, 78.9629]}
              zoom={5}
              style={{ height: '100%', width: '100%' }}
              zoomControl={false}
            >
              <TileLayer
                attribution='&copy; OpenStreetMap'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </MapContainer>
          </div>
        )}

        {/* ── Stats Row ────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={<AlertTriangle className="w-5 h-5" />}
            label="Total events today"
            value="363"
            sub="+12% vs yesterday"
            trend="up"
          />
          <StatCard
            icon={<Car className="w-5 h-5" />}
            label="Active hazards"
            value="19"
            sub="3 critical"
            trend="neutral"
          />
          <StatCard
            icon={<Star className="w-5 h-5" />}
            label="Avg road quality"
            value="6.4"
            sub="Out of 10"
            trend="neutral"
          />
          <StatCard
            icon={<ParkingSquare className="w-5 h-5" />}
            label="Parking observations"
            value="1,247"
            sub="-5% vs yesterday"
            trend="down"
          />
        </div>

        {/* ── Charts Row ───────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Line chart — events over 7 days */}
          <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 mb-4">Road Events — Last 7 Days</h2>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={TIMELINE_DATA}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#f9fafb' }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="potholes"     stroke="#ef4444" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="construction" stroke="#f97316" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="waterlogging" stroke="#3b82f6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="obstacles"    stroke="#a855f7" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Pie chart — severity distribution */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 mb-4">Severity Distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={SEVERITY_DATA}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={3}
                  label={({ name, percent }) =>
                    `${name} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {SEVERITY_DATA.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Bar chart — events by type */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Events by Type</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={BY_TYPE_DATA} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
              <XAxis dataKey="type" tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {BY_TYPE_DATA.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* ── Recent Events Table ───────────────────────────────────────────── */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800">
            <h2 className="text-sm font-semibold text-gray-300">Recent Road Events</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                  <th className="px-5 py-3">ID</th>
                  <th className="px-5 py-3">Type</th>
                  <th className="px-5 py-3">Severity</th>
                  <th className="px-5 py-3">Location</th>
                  <th className="px-5 py-3">Time</th>
                  <th className="px-5 py-3">Confidence</th>
                  <th className="px-5 py-3">Description</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_RECENT_EVENTS.map((evt, i) => (
                  <tr
                    key={evt.id}
                    className={clsx(
                      'border-b border-gray-800 hover:bg-gray-800/50 transition-colors',
                      i % 2 === 0 ? 'bg-gray-900' : 'bg-gray-900/50'
                    )}
                  >
                    <td className="px-5 py-3 font-mono text-xs text-gray-400">{evt.id}</td>
                    <td className="px-5 py-3 text-white capitalize">
                      {evt.event_type.replace(/_/g, ' ')}
                    </td>
                    <td className="px-5 py-3">
                      <SeverityBadge sev={evt.severity} />
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-gray-400">
                      {(evt.location?.lat ?? evt.lat ?? 0).toFixed(4)}, {(evt.location?.lon ?? evt.lon ?? 0).toFixed(4)}
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs whitespace-nowrap">
                      {format(new Date(evt.reported_at ?? evt.observed_at ?? Date.now()), 'dd MMM HH:mm')}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-500 rounded-full"
                            style={{ width: `${evt.confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400">
                          {Math.round(evt.confidence * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs max-w-xs truncate">
                      {evt.description ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer padding */}
        <div className="h-4" />
      </div>
    </div>
  );
}
