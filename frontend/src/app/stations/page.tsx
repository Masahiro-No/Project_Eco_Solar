"use client";

import React, { useState, useEffect } from 'react';
import {
  MapPinIcon,
  RadioTowerIcon,
  ZapIcon,
  CheckCircle2Icon,
  SearchIcon,
  PlusIcon,
  XIcon,
  RefreshCwIcon,
  CompassIcon,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Panel } from '@/components/UI/Panel';
import { stations as defaultStations, StationDashboardItem } from '@/data/dashboard';
import { solarApi, StationCreateRequest, NearestStationResponse } from '@/services/api';

export default function StationsPage() {
  const t = useTranslations('common');
  const [stationList, setStationList] = useState<StationDashboardItem[]>(defaultStations);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'online' | 'offline'>('all');
  const [isLoading, setIsLoading] = useState(false);

  // Modals state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showNearestModal, setShowNearestModal] = useState(false);
  const [nearestResult, setNearestResult] = useState<NearestStationResponse | null>(null);

  // New Station Form State
  const [newStation, setNewStation] = useState<StationCreateRequest>({
    id: `ST-00${stationList.length + 1}`,
    name: '',
    latitude: 7.0086,
    longitude: 100.4988,
    panel_area: 25000,
    efficiency: 0.185,
    target_capacity_kw: 4000,
  });

  // Nearest query form
  const [queryLat, setQueryLat] = useState('7.0086');
  const [queryLon, setQueryLon] = useState('100.4988');

  // Load from API on mount
  useEffect(() => {
    async function loadStations() {
      setIsLoading(true);
      const apiStations = await solarApi.getStations();
      if (apiStations && apiStations.length > 0) {
        // Merge API stations with operational display fields
        const merged: StationDashboardItem[] = apiStations.map((s) => {
          const defaultMatch = defaultStations.find((d) => d.id === s.id);
          const pgen = defaultMatch ? defaultMatch.pgen : Math.round(s.target_capacity_kw * 0.82);
          return {
            id: s.id,
            name: s.name,
            province: defaultMatch?.province || 'Southern Region',
            latitude: s.latitude,
            longitude: s.longitude,
            panel_area: s.panel_area,
            efficiency: s.efficiency,
            target_capacity_kw: s.target_capacity_kw,
            is_active: s.is_active,
            pgen: s.is_active ? pgen : 0,
            ptarget: s.target_capacity_kw,
            online: s.is_active,
            inverters: defaultMatch?.inverters || `${Math.round(s.target_capacity_kw / 500)}/${Math.round(s.target_capacity_kw / 500)}`,
            pr: defaultMatch?.pr || `${(s.efficiency * 100 * 4.6).toFixed(1)}%`,
            temp: defaultMatch?.temp || '32.0°C',
          };
        });
        setStationList(merged);
      }
      setIsLoading(false);
    }
    loadStations();
  }, []);

  // Filter
  const filtered = stationList.filter((s) => {
    const matchesSearch =
      s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.province.includes(searchTerm);
    const matchesStatus =
      filterStatus === 'all' || (filterStatus === 'online' ? s.is_active : !s.is_active);
    return matchesSearch && matchesStatus;
  });

  const totalCapacity = stationList.reduce((sum, s) => sum + s.target_capacity_kw, 0);
  const totalArea = stationList.reduce((sum, s) => sum + s.panel_area, 0);
  const totalPgen = stationList.reduce((sum, s) => sum + s.pgen, 0);
  const onlineCount = stationList.filter((s) => s.is_active).length;

  // Handle Add Station
  const handleCreateStation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStation.name) return;

    // Call backend API (with graceful local fallback)
    const res = await solarApi.createStation(newStation);

    const createdItem: StationDashboardItem = {
      id: res?.id || newStation.id || `ST-00${stationList.length + 1}`,
      name: newStation.name,
      province: 'Southern Region',
      latitude: newStation.latitude,
      longitude: newStation.longitude,
      panel_area: newStation.panel_area,
      efficiency: newStation.efficiency,
      target_capacity_kw: newStation.target_capacity_kw,
      is_active: true,
      pgen: Math.round(newStation.target_capacity_kw * 0.8),
      ptarget: newStation.target_capacity_kw,
      online: true,
      inverters: `${Math.round(newStation.target_capacity_kw / 500)}/${Math.round(newStation.target_capacity_kw / 500)}`,
      pr: `${(newStation.efficiency * 100 * 4.6).toFixed(1)}%`,
      temp: '32.0°C',
    };

    setStationList((prev) => [createdItem, ...prev]);
    setShowCreateModal(false);
    setNewStation({
      id: `ST-00${stationList.length + 2}`,
      name: '',
      latitude: 7.0086,
      longitude: 100.4988,
      panel_area: 25000,
      efficiency: 0.185,
      target_capacity_kw: 4000,
    });
  };

  // Handle Soft-Delete
  const handleToggleActive = async (id: string, currentActive: boolean) => {
    if (currentActive) {
      await solarApi.deleteStation(id);
    } else {
      await solarApi.restoreStation(id);
    }
    setStationList((prev) =>
      prev.map((s) =>
        s.id === id
          ? { ...s, is_active: !currentActive, online: !currentActive, pgen: !currentActive ? Math.round(s.target_capacity_kw * 0.8) : 0 }
          : s
      )
    );
  };

  // Handle Find Nearest
  const handleFindNearest = async (e: React.FormEvent) => {
    e.preventDefault();
    const lat = parseFloat(queryLat);
    const lon = parseFloat(queryLon);
    if (isNaN(lat) || isNaN(lon)) return;

    // Call API or calculate locally
    const res = await solarApi.findNearestStation(lat, lon);
    if (res) {
      setNearestResult(res);
    } else {
      // Local fallback calculation (Haversine formula)
      let minDistance = Infinity;
      let nearestItem = stationList[0];
      stationList.forEach((s) => {
        const dLat = ((s.latitude - lat) * Math.PI) / 180;
        const dLon = ((s.longitude - lon) * Math.PI) / 180;
        const a =
          Math.sin(dLat / 2) * Math.sin(dLat / 2) +
          Math.cos((lat * Math.PI) / 180) *
            Math.cos((s.latitude * Math.PI) / 180) *
            Math.sin(dLon / 2) *
            Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        const dist = 6371 * c; // Earth radius in km
        if (dist < minDistance) {
          minDistance = dist;
          nearestItem = s;
        }
      });
      setNearestResult({
        station_id: nearestItem.id,
        name: nearestItem.name,
        latitude: nearestItem.latitude,
        longitude: nearestItem.longitude,
        target_capacity_kw: nearestItem.target_capacity_kw,
        distance_km: Math.round(minDistance * 10) / 10,
      });
    }
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <MapPinIcon className="h-6 w-6" strokeWidth={2.2} />
          </span>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-[22px] font-bold leading-tight text-[#0f1f4d]">
                {t('stations_page_title')}
              </h1>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-600 border border-slate-200">
                {t('fastapi_route_badge')}
              </span>
            </div>
            <p className="text-[13.5px] text-slate-600">{t('stations_page_desc')}</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowNearestModal(true)}
            className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-2 text-[13px] font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <CompassIcon className="h-4 w-4 text-brand" />
            {t('station_btn_nearest')}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-brand/90"
          >
            <PlusIcon className="h-4 w-4" />
            {t('station_btn_add')}
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-3.5">
        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
            <RadioTowerIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_stations')}</p>
            <p className="text-[25px] font-bold text-ink">
              {stationList.length} <span className="text-[15px] font-normal text-muted">{t('unit_station')}</span>
            </p>
            <p className="text-[11.5px] text-slate-500">{t('total_area_desc')} {totalArea.toLocaleString()} m²</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <CheckCircle2Icon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('online_status')}</p>
            <p className="text-[25px] font-bold text-ok">
              {onlineCount} <span className="text-[15px] font-normal text-slate-500">/ {stationList.length}</span>
            </p>
            <p className="text-[11.5px] text-slate-500">{t('grid_ready')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ok-soft text-ok">
            <ZapIcon className="h-5 w-5" fill="currentColor" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_current_pgen')}</p>
            <p className="text-[25px] font-bold text-ink">
              {totalPgen.toLocaleString()} <span className="text-[15px] font-normal text-muted">kW</span>
            </p>
            <p className="text-[11.5px] text-slate-500">{t('from_sensors_lstm')}</p>
          </div>
        </article>

        <article className="flex gap-3.5 rounded-xl border border-line bg-white p-3.5 shadow-sm">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
            <ZapIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-medium text-slate-600">{t('total_target_pgen')}</p>
            <p className="text-[25px] font-bold text-ink">
              {totalCapacity.toLocaleString()} <span className="text-[15px] font-normal text-muted">kW</span>
            </p>
            <p className="text-[11.5px] text-slate-500">{t('installed_target_desc')}</p>
          </div>
        </article>
      </div>

      {/* Main Table Panel */}
      <Panel
        title={t('station_list_title')}
        icon={<MapPinIcon className="h-5 w-5 text-brand" />}
        action={
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            {isLoading && <span className="animate-spin text-brand"><RefreshCwIcon className="h-3.5 w-3.5" /></span>}
            <span>{t('schema_station_response')}</span>
          </div>
        }
      >
        {/* Filter Toolbar */}
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder={t('search_station_placeholder')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-9.5 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-[13.5px] text-ink placeholder:text-muted focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[13px] font-medium text-slate-600">{t('filter_status')}</span>
            <div className="flex rounded-lg border border-line bg-canvas p-0.5 text-[12.5px] font-medium">
              <button
                onClick={() => setFilterStatus('all')}
                className={`rounded-md px-3 py-1 transition-colors ${
                  filterStatus === 'all'
                    ? 'bg-white shadow-sm font-semibold text-brand'
                    : 'text-slate-600 hover:text-ink'
                }`}
              >
                {t('filter_all')}
              </button>
              <button
                onClick={() => setFilterStatus('online')}
                className={`rounded-md px-3 py-1 transition-colors ${
                  filterStatus === 'online'
                    ? 'bg-white shadow-sm font-semibold text-ok'
                    : 'text-slate-600 hover:text-ink'
                }`}
              >
                {t('online')} ({onlineCount})
              </button>
              <button
                onClick={() => setFilterStatus('offline')}
                className={`rounded-md px-3 py-1 transition-colors ${
                  filterStatus === 'offline'
                    ? 'bg-white shadow-sm font-semibold text-bad'
                    : 'text-slate-600 hover:text-ink'
                }`}
              >
                {t('offline')} ({stationList.length - onlineCount})
              </button>
            </div>
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line bg-canvas font-bold text-slate-700">
              <tr>
                <th className="px-4 py-3">{t('station_id')}</th>
                <th className="px-4 py-3">{t('th_station_name')}</th>
                <th className="px-4 py-3">{t('station_coordinates')}</th>
                <th className="px-4 py-3 text-right">{t('station_panel_area')}</th>
                <th className="px-4 py-3 text-center">{t('station_efficiency')}</th>
                <th className="px-4 py-3 text-right">{t('station_target_kw')}</th>
                <th className="px-4 py-3 text-right">{t('station_current_kw')}</th>
                <th className="px-4 py-3 text-center">{t('th_status')}</th>
                <th className="px-4 py-3 text-center">{t('station_actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {filtered.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50/70 transition-colors">
                  <td className="px-4 py-3 font-bold text-brand tabular-nums">
                    <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[12px]">{s.id}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-bold text-ink">{s.name}</div>
                    <div className="text-[11px] text-slate-500">{s.province}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600 tabular-nums font-mono text-[12px]">
                    {s.latitude.toFixed(4)}, {s.longitude.toFixed(4)}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-slate-700 tabular-nums">
                    {s.panel_area.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-center font-medium text-slate-700 tabular-nums">
                    {(s.efficiency * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-700 tabular-nums">
                    {s.target_capacity_kw.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right font-bold text-ink tabular-nums">
                    {s.is_active ? s.pgen.toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-bold ${
                        s.is_active ? 'bg-ok-soft text-ok' : 'bg-bad-soft text-bad'
                      }`}
                    >
                      <span className={`h-2 w-2 rounded-full ${s.is_active ? 'bg-ok' : 'bg-bad'}`} />
                      {s.is_active ? t('online') : t('offline')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleToggleActive(s.id, s.is_active)}
                      className={`rounded px-2.5 py-1 text-[11.5px] font-semibold transition ${
                        s.is_active
                          ? 'border border-red-200 text-bad hover:bg-bad-soft'
                          : 'border border-ok/30 text-ok hover:bg-ok-soft'
                      }`}
                    >
                      {s.is_active ? t('soft_delete_action') : t('restore_action')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Modal: Create Station */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <PlusIcon className="h-5 w-5" />
                </span>
                <h2 className="text-[17px] font-bold text-ink">{t('station_modal_add_title')}</h2>
              </div>
              <button onClick={() => setShowCreateModal(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
                <XIcon className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreateStation} className="mt-4 flex flex-col gap-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('station_id_label')}</label>
                  <input
                    type="text"
                    required
                    value={newStation.id || ''}
                    onChange={(e) => setNewStation({ ...newStation, id: e.target.value })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                    placeholder={t('station_id_placeholder')}
                  />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('station_name_label')}</label>
                  <input
                    type="text"
                    required
                    value={newStation.name}
                    onChange={(e) => setNewStation({ ...newStation, name: e.target.value })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                    placeholder={t('station_name_placeholder')}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('latitude')}</label>
                  <input
                    type="number"
                    step="0.0001"
                    required
                    value={newStation.latitude}
                    onChange={(e) => setNewStation({ ...newStation, latitude: parseFloat(e.target.value) })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('longitude')}</label>
                  <input
                    type="number"
                    step="0.0001"
                    required
                    value={newStation.longitude}
                    onChange={(e) => setNewStation({ ...newStation, longitude: parseFloat(e.target.value) })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('station_panel_area')}</label>
                  <input
                    type="number"
                    required
                    value={newStation.panel_area}
                    onChange={(e) => setNewStation({ ...newStation, panel_area: parseFloat(e.target.value) })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('station_efficiency')}</label>
                  <input
                    type="number"
                    step="0.001"
                    max="1"
                    min="0"
                    required
                    value={newStation.efficiency}
                    onChange={(e) => setNewStation({ ...newStation, efficiency: parseFloat(e.target.value) })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-slate-700">{t('station_target_kw')}</label>
                  <input
                    type="number"
                    required
                    value={newStation.target_capacity_kw}
                    onChange={(e) => setNewStation({ ...newStation, target_capacity_kw: parseFloat(e.target.value) })}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] focus:border-brand focus:outline-none"
                  />
                </div>
              </div>

              <div className="mt-4 flex items-center justify-end gap-2 pt-2 border-t border-line">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded-lg border border-line px-4 py-2 text-[13px] font-medium text-slate-600 hover:bg-slate-50"
                >
                  {t('cancel')}
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand px-5 py-2 text-[13px] font-bold text-white shadow-sm hover:bg-brand/90"
                >
                  {t('save_station')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Find Nearest Station */}
      {showNearestModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <CompassIcon className="h-5 w-5" />
                </span>
                <h2 className="text-[17px] font-bold text-ink">{t('station_modal_nearest_title')}</h2>
              </div>
              <button onClick={() => setShowNearestModal(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100">
                <XIcon className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleFindNearest} className="mt-4 flex flex-col gap-3">
              <p className="text-[12.5px] text-slate-600">
                {t('station_modal_nearest_desc')}
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12px] font-medium text-slate-700">{t('latitude')}</label>
                  <input
                    type="text"
                    required
                    value={queryLat}
                    onChange={(e) => setQueryLat(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] font-mono focus:border-brand focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[12px] font-medium text-slate-700">{t('longitude')}</label>
                  <input
                    type="text"
                    required
                    value={queryLon}
                    onChange={(e) => setQueryLon(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-line px-3 text-[13px] font-mono focus:border-brand focus:outline-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="mt-2 rounded-lg bg-brand px-4 py-2 text-[13px] font-bold text-white shadow-sm hover:bg-brand/90"
              >
                {t('station_btn_nearest')}
              </button>
            </form>

            {nearestResult && (
              <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
                <div className="flex items-center gap-2 text-emerald-800 font-bold text-[14px]">
                  <CheckCircle2Icon className="h-4.5 w-4.5 text-emerald-600" />
                  {t('station_found_nearest')}
                </div>
                <div className="mt-2 text-[13.5px] font-bold text-ink">{nearestResult.name}</div>
                <div className="mt-1 flex items-center justify-between text-[12px] text-slate-600">
                  <span>{t('station_id_label')}: <strong className="text-brand">{nearestResult.station_id}</strong></span>
                  <span>{t('distance_km')} <strong className="text-emerald-700">{nearestResult.distance_km} km</strong></span>
                  <span>{t('target_capacity')} <strong>{nearestResult.target_capacity_kw} kW</strong></span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
