"use client";

// Client-only: imports Leaflet (needs `window`). Load it with next/dynamic({ ssr: false }).
import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export type ExistingPoint = { lat: number; lng: number; name: string };

type Props = {
  latitude: number;
  longitude: number;
  onChange: (lat: number, lng: number) => void;
  /** Already-registered stations, drawn as small grey dots for context */
  existing?: ExistingPoint[];
  heightClass?: string;
  /** Text for the "use my location" button; omit to hide it */
  myLocationLabel?: string;
};

const PIN_SVG = `
<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40">
  <path d="M15 1C7.3 1 1 7.2 1 14.8 1 25 15 39 15 39s14-14 14-24.2C29 7.2 22.7 1 15 1z" fill="#1d4ed8" stroke="#fff" stroke-width="2"/>
  <circle cx="15" cy="15" r="5.5" fill="#fff"/>
</svg>`;

const round5 = (v: number) => Math.round(v * 1e5) / 1e5;

export function LocationPicker({
  latitude,
  longitude,
  onChange,
  existing = [],
  heightClass = 'h-[260px]',
  myLocationLabel,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Create the map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, { zoomControl: true, attributionControl: true }).setView(
      [latitude, longitude],
      9
    );
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const marker = L.marker([latitude, longitude], {
      draggable: true,
      autoPan: true,
      icon: L.divIcon({ className: '', html: PIN_SVG, iconSize: [30, 40], iconAnchor: [15, 39] }),
    }).addTo(map);

    const commit = (ll: L.LatLng) => {
      const wrapped = map.wrapLatLng(ll);
      const lat = round5(Math.max(-90, Math.min(90, wrapped.lat)));
      const lng = round5(wrapped.lng);
      marker.setLatLng([lat, lng]);
      onChangeRef.current(lat, lng);
    };

    map.on('click', (e: L.LeafletMouseEvent) => commit(e.latlng));
    marker.on('dragend', () => commit(marker.getLatLng()));

    mapRef.current = map;
    markerRef.current = marker;

    // The container may have just become visible (modal): make Leaflet re-measure it
    const t = setTimeout(() => map.invalidateSize(), 50);

    return () => {
      clearTimeout(t);
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the marker in sync when the coordinates change from outside (e.g. form reset)
  useEffect(() => {
    const marker = markerRef.current;
    const map = mapRef.current;
    if (!marker || !map || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
    const cur = marker.getLatLng();
    if (Math.abs(cur.lat - latitude) > 1e-6 || Math.abs(cur.lng - longitude) > 1e-6) {
      marker.setLatLng([latitude, longitude]);
      if (!map.getBounds().contains([latitude, longitude])) map.panTo([latitude, longitude]);
    }
  }, [latitude, longitude]);

  // Existing stations (context only)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    existing.forEach((p) => {
      L.circleMarker([p.lat, p.lng], {
        radius: 5,
        color: '#fff',
        weight: 1.5,
        fillColor: '#64748b',
        fillOpacity: 0.9,
      })
        .bindTooltip(p.name)
        .addTo(layer);
    });
    return () => {
      layer.remove();
    };
  }, [existing]);

  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = round5(pos.coords.latitude);
        const lng = round5(pos.coords.longitude);
        mapRef.current?.setView([lat, lng], 13);
        markerRef.current?.setLatLng([lat, lng]);
        onChangeRef.current(lat, lng);
      },
      () => {
        /* permission denied or unavailable: keep the current pin */
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  return (
    <div className="relative isolate">
      <div
        ref={containerRef}
        className={`${heightClass} w-full overflow-hidden rounded-lg border border-line`}
        role="application"
        aria-label="Map: click to place the station pin"
      />
      {myLocationLabel && (
        <button
          type="button"
          onClick={useMyLocation}
          className="absolute bottom-6 left-2 z-[500] rounded-md border border-line bg-white px-2.5 py-1 text-[11.5px] font-semibold text-slate-700 shadow hover:bg-slate-50"
        >
          {myLocationLabel}
        </button>
      )}
    </div>
  );
}

export default LocationPicker;
