import { create } from 'zustand';
import type {
  GPSCoord,
  RoadEvent,
  ParkingObservation,
  RouteOption,
  HazardAlert,
  SpeedAdvisory,
} from '@/types';

interface MapState {
  // ─── State ─────────────────────────────────────────────────────────────────
  currentPosition:     GPSCoord | null;
  roadEvents:          RoadEvent[];
  parkingObservations: ParkingObservation[];
  activeRoute:         RouteOption | null;
  hazardAlerts:        HazardAlert[];
  speedAdvisory:       SpeedAdvisory | null;
  mapCenter:           [number, number];
  mapZoom:             number;

  // ─── Actions ───────────────────────────────────────────────────────────────
  setPosition:             (pos: GPSCoord) => void;
  setRoadEvents:           (events: RoadEvent[]) => void;
  setParkingObservations:  (obs: ParkingObservation[]) => void;
  setActiveRoute:          (route: RouteOption | null) => void;
  addHazardAlert:          (alert: HazardAlert) => void;
  dismissHazardAlert:      (id: string) => void;
  setSpeedAdvisory:        (advisory: SpeedAdvisory | null) => void;
  setMapView:              (center: [number, number], zoom: number) => void;
}

export const useMapStore = create<MapState>((set) => ({
  // ─── Initial State ─────────────────────────────────────────────────────────
  currentPosition:     null,
  roadEvents:          [],
  parkingObservations: [],
  activeRoute:         null,
  hazardAlerts:        [],
  speedAdvisory:       null,
  mapCenter:           [20.5937, 78.9629], // India center
  mapZoom:             5,

  // ─── Action Implementations ───────────────────────────────────────────────
  setPosition: (pos) => set({ currentPosition: pos }),

  setRoadEvents: (events) => set({ roadEvents: events }),

  setParkingObservations: (obs) => set({ parkingObservations: obs }),

  setActiveRoute: (route) => set({ activeRoute: route }),

  addHazardAlert: (alert) =>
    set((state) => ({
      hazardAlerts: [alert, ...state.hazardAlerts].slice(0, 10), // keep latest 10
    })),

  dismissHazardAlert: (id) =>
    set((state) => ({
      hazardAlerts: state.hazardAlerts.filter((a) => a.id !== id),
    })),

  setSpeedAdvisory: (advisory) => set({ speedAdvisory: advisory }),

  setMapView: (center, zoom) => set({ mapCenter: center, mapZoom: zoom }),
}));
