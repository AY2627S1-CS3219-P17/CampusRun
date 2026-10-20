// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: AI-generated shared NUS map geometry and coordinate validation.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-20
// Scope: AI-added the default view, the middle 80% of the served area.
// Author review: <to be completed by author>

import type { LatLngExpression } from 'leaflet'

export type MapPosition = { latitude: number; longitude: number }

export const NUS_SERVED_AREA = {
  minLat: 1.287,
  maxLat: 1.31,
  minLng: 103.764,
  maxLng: 103.788,
} as const

export const NUS_CENTER: LatLngExpression = [1.2985, 103.776]
export const MAP_LIMITS = {
  minLat: 1.25,
  maxLat: 1.35,
  minLng: 103.72,
  maxLng: 103.83,
} as const

export const SERVED_BOUNDS: [[number, number], [number, number]] = [
  [NUS_SERVED_AREA.minLat, NUS_SERVED_AREA.minLng],
  [NUS_SERVED_AREA.maxLat, NUS_SERVED_AREA.maxLng],
]
// What a map without a pin opens on: the middle 80% of the served area
const latInset = (NUS_SERVED_AREA.maxLat - NUS_SERVED_AREA.minLat) * 0.1
const lngInset = (NUS_SERVED_AREA.maxLng - NUS_SERVED_AREA.minLng) * 0.1
export const DEFAULT_VIEW_BOUNDS: [[number, number], [number, number]] = [
  [NUS_SERVED_AREA.minLat + latInset, NUS_SERVED_AREA.minLng + lngInset],
  [NUS_SERVED_AREA.maxLat - latInset, NUS_SERVED_AREA.maxLng - lngInset],
]
export const OUTER_RING: LatLngExpression[] = [
  [MAP_LIMITS.minLat, MAP_LIMITS.minLng],
  [MAP_LIMITS.maxLat, MAP_LIMITS.minLng],
  [MAP_LIMITS.maxLat, MAP_LIMITS.maxLng],
  [MAP_LIMITS.minLat, MAP_LIMITS.maxLng],
]
export const SERVED_AREA_HOLE: LatLngExpression[] = [
  [NUS_SERVED_AREA.minLat, NUS_SERVED_AREA.minLng],
  [NUS_SERVED_AREA.minLat, NUS_SERVED_AREA.maxLng],
  [NUS_SERVED_AREA.maxLat, NUS_SERVED_AREA.maxLng],
  [NUS_SERVED_AREA.maxLat, NUS_SERVED_AREA.minLng],
]

export function isInsideNus(position: MapPosition) {
  return (
    position.latitude >= NUS_SERVED_AREA.minLat &&
    position.latitude <= NUS_SERVED_AREA.maxLat &&
    position.longitude >= NUS_SERVED_AREA.minLng &&
    position.longitude <= NUS_SERVED_AREA.maxLng
  )
}
