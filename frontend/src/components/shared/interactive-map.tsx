// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: AI-generated NUS-bounded Leaflet map with editable and read-only fullscreen modes; optional two-pin pickup/dropoff display.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Removed redundant usage comments from the typed single- and two-pin map modes.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-20
// Scope: AI-added the wider default view, flying to a chosen position, and the red pin option.
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
  useMap,
  useMapEvents,
} from 'react-leaflet'
import {
  DEFAULT_VIEW_BOUNDS,
  MAP_LIMITS,
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

const dropoffIcon = divIcon({
  className: 'interactive-map-marker',
  html: '<span class="interactive-map-pin interactive-map-pin-dropoff"></span>',
  iconSize: [40, 40],
  iconAnchor: [20, 38],
})

const redIcon = divIcon({
  className: 'interactive-map-marker',
  html: '<span class="interactive-map-pin interactive-map-pin-red"></span>',
  iconSize: [40, 40],
  iconAnchor: [20, 38],
})

type TwoPins = { pickup: MapPosition; dropoff: MapPosition }

// Zooms in on the position each time it changes
function FlyTo({ position }: { position: MapPosition }) {
  const map = useMap()
  const { latitude, longitude } = position

  useEffect(() => {
    map.flyTo([latitude, longitude], 17, { duration: 0.6 })
  }, [map, latitude, longitude])

  return null
}

function FitTwoPins({
  pins,
  fullscreen,
}: {
  pins: TwoPins
  fullscreen: boolean
}) {
  const map = useMap()
  const { latitude: pickupLat, longitude: pickupLng } = pins.pickup
  const { latitude: dropoffLat, longitude: dropoffLng } = pins.dropoff

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      map.invalidateSize()
      map.fitBounds(
        [
          [pickupLat, pickupLng],
          [dropoffLat, dropoffLng],
        ],
        { padding: [40, 40], maxZoom: 17, animate: false },
      )
    })
    return () => cancelAnimationFrame(frame)
  }, [map, pickupLat, pickupLng, dropoffLat, dropoffLng, fullscreen])

  return null
}

function Pin({
  position,
  onChange,
  readOnly,
  red,
}: {
  position: MapPosition | null
  onChange?: (position: MapPosition) => void
  readOnly: boolean
  red: boolean
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
      icon={red ? redIcon : markerIcon}
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
  ariaLabel?: string
  className?: string
  // The map flies here whenever it changes, e.g. when a predefined location is picked
  focus?: MapPosition | null
  redPin?: boolean
} & (
  | ({ value: MapPosition | null; pins?: never } & (
      | { readOnly: true; onChange?: never }
      | { readOnly?: false; onChange: (position: MapPosition) => void }
    ))
  | { pins: TwoPins; value?: never; readOnly: true; onChange?: never }
)

export default function InteractiveMap({
  value,
  pins,
  onChange,
  readOnly = false,
  ariaLabel,
  className,
  focus,
  redPin = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap>(null)
  const editingRef = useRef(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [draft, setDraft] = useState<MapPosition | null>(value ?? null)

  useEffect(() => {
    const handleChange = () => {
      const active = document.fullscreenElement === containerRef.current
      setFullscreen(active)

      if (!active && editingRef.current) {
        editingRef.current = false
        setDraft(value ?? null)
      }
      requestAnimationFrame(() => mapRef.current?.invalidateSize())
    }
    document.addEventListener('fullscreenchange', handleChange)
    return () => document.removeEventListener('fullscreenchange', handleChange)
  }, [value])

  async function openFullscreen() {
    setDraft(value ?? null)
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

  const displayedPosition = fullscreen ? draft : (value ?? null)

  return (
    <div
      ref={containerRef}
      className={`interactive-map${className ? ` ${className}` : ''}`}
      aria-label={
        ariaLabel ??
        (pins
          ? 'Pickup and dropoff locations on the map'
          : 'Choose a location on the map')
      }
    >
      <MapContainer
        ref={mapRef}
        {...(value
          ? { center: [value.latitude, value.longitude], zoom: 17 }
          : { bounds: DEFAULT_VIEW_BOUNDS })}
        // Fractional zoom, so the default view fits the area closely in a short map
        zoomSnap={0.25}
        minZoom={13}
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
        {pins ? (
          <>
            <FitTwoPins pins={pins} fullscreen={fullscreen} />
            <Marker
              position={[pins.pickup.latitude, pins.pickup.longitude]}
              icon={markerIcon}
              alt="Pickup location"
              interactive={false}
            />
            <Marker
              position={[pins.dropoff.latitude, pins.dropoff.longitude]}
              icon={dropoffIcon}
              alt="Dropoff location"
              interactive={false}
            />
          </>
        ) : (
          <Pin
            position={displayedPosition}
            onChange={changePosition}
            readOnly={readOnly}
            red={redPin}
          />
        )}
        {focus && <FlyTo position={focus} />}
      </MapContainer>

      {pins && (
        <div className="interactive-map-legend" aria-label="Map pins">
          <span>
            <i className="interactive-map-legend-pickup" aria-hidden="true" />
            Pickup
          </span>
          <span>
            <i className="interactive-map-legend-dropoff" aria-hidden="true" />
            Dropoff
          </span>
        </div>
      )}

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
