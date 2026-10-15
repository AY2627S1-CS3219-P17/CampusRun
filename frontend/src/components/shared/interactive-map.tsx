// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: AI-generated NUS-bounded Leaflet map with editable and read-only fullscreen modes.
// Author review: <to be completed by author>

import { useEffect, useRef, useState } from 'react'
import {
  divIcon,
  type Map as LeafletMap,
  type Marker as LeafletMarker,
} from 'leaflet'
import { Check, Maximize2, Minimize2 } from 'lucide-react'
import {
  MapContainer,
  Marker,
  Polygon,
  Rectangle,
  TileLayer,
  useMapEvents,
} from 'react-leaflet'
import {
  MAP_LIMITS,
  NUS_CENTER,
  OUTER_RING,
  SERVED_AREA_HOLE,
  SERVED_BOUNDS,
  isInsideNus,
  type MapPosition,
} from '../../utils/map'
import 'leaflet/dist/leaflet.css'
import './interactive-map.css'

const markerIcon = divIcon({
  className: 'interactive-map-marker',
  html: '<span class="interactive-map-pin"></span>',
  iconSize: [40, 40],
  iconAnchor: [20, 38],
})

function Pin({
  position,
  onChange,
  readOnly,
}: {
  position: MapPosition | null
  onChange?: (position: MapPosition) => void
  readOnly: boolean
}) {
  const markerRef = useRef<LeafletMarker>(null)

  useMapEvents({
    click: ({ latlng }) => {
      const next = { latitude: latlng.lat, longitude: latlng.lng }
      if (!readOnly && isInsideNus(next)) onChange?.(next)
    },
  })

  return position ? (
    <Marker
      ref={markerRef}
      position={[position.latitude, position.longitude]}
      icon={markerIcon}
      alt="Selected location"
      draggable={!readOnly}
      interactive={!readOnly}
      eventHandlers={{
        dragend: () => {
          const marker = markerRef.current
          if (!marker) return
          const { lat, lng } = marker.getLatLng()
          const next = { latitude: lat, longitude: lng }
          if (isInsideNus(next)) onChange?.(next)
          else marker.setLatLng([position.latitude, position.longitude])
        },
      }}
    />
  ) : null
}

type Props = {
  value: MapPosition | null
  ariaLabel?: string
  className?: string
} & (
  | { readOnly: true; onChange?: never }
  | { readOnly?: false; onChange: (position: MapPosition) => void }
)

export default function InteractiveMap({
  value,
  onChange,
  readOnly = false,
  ariaLabel = 'Choose a location on the map',
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap>(null)
  const editingRef = useRef(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [draft, setDraft] = useState(value)

  useEffect(() => {
    const handleChange = () => {
      const active = document.fullscreenElement === containerRef.current
      setFullscreen(active)

      if (!active && editingRef.current) {
        editingRef.current = false
        setDraft(value)
      }
      requestAnimationFrame(() => mapRef.current?.invalidateSize())
    }
    document.addEventListener('fullscreenchange', handleChange)
    return () => document.removeEventListener('fullscreenchange', handleChange)
  }, [value])

  async function openFullscreen() {
    setDraft(value)
    if (!readOnly) editingRef.current = true
    try {
      await containerRef.current?.requestFullscreen()
    } catch (error) {
      editingRef.current = false
      throw error
    }
  }

  async function saveAndClose() {
    if (!readOnly && draft) onChange?.(draft)
    editingRef.current = false
    await document.exitFullscreen()
  }

  function changePosition(position: MapPosition) {
    if (readOnly) return
    if (editingRef.current) setDraft(position)
    else onChange?.(position)
  }

  const displayedPosition = fullscreen ? draft : value

  return (
    <div
      ref={containerRef}
      className={`interactive-map${className ? ` ${className}` : ''}`}
      aria-label={ariaLabel}
    >
      <MapContainer
        ref={mapRef}
        center={value ? [value.latitude, value.longitude] : NUS_CENTER}
        zoom={17}
        minZoom={14}
        maxBounds={[
          [MAP_LIMITS.minLat, MAP_LIMITS.minLng],
          [MAP_LIMITS.maxLat, MAP_LIMITS.maxLng],
        ]}
        maxBoundsViscosity={1}
        scrollWheelZoom={false}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <Polygon
          positions={[OUTER_RING, SERVED_AREA_HOLE]}
          interactive={false}
          pathOptions={{
            stroke: false,
            fillColor: '#d92d20',
            fillOpacity: 0.18,
            fillRule: 'evenodd',
          }}
        />
        <Rectangle
          bounds={SERVED_BOUNDS}
          interactive={false}
          pathOptions={{ color: '#b42318', weight: 2, fill: false }}
        />
        <Pin
          position={displayedPosition}
          onChange={changePosition}
          readOnly={readOnly}
        />
      </MapContainer>

      {document.fullscreenEnabled && (
        <button
          className={`interactive-map-fullscreen${fullscreen ? ' is-close' : ''}`}
          type="button"
          aria-label={
            fullscreen
              ? readOnly
                ? 'Exit fullscreen map'
                : 'Save location and close'
              : 'View map fullscreen'
          }
          aria-pressed={fullscreen}
          onClick={() => void (fullscreen ? saveAndClose() : openFullscreen())}
        >
          {fullscreen && readOnly ? (
            <>
              <Minimize2 size={17} aria-hidden="true" />
              Exit fullscreen
            </>
          ) : fullscreen ? (
            <>
              <Check size={17} aria-hidden="true" />
              Save &amp; close
            </>
          ) : (
            <Maximize2 size={18} aria-hidden="true" />
          )}
        </button>
      )}
    </div>
  )
}
