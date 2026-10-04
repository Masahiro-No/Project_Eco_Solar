"use client";

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  MapPinIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  SunIcon,
  UserIcon,
  SettingsIcon,
  LogOutIcon,
  LogInIcon,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useLanguage } from '@/context/LanguageContext';
import { useAuth } from '@/context/AuthContext';
import { useForecast } from '@/context/ForecastContext';

type TopBarProps = {
  target?: string;
  onTargetChange?: (v: string) => void;
};

export function TopBar({ target, onTargetChange }: TopBarProps) {
  const t = useTranslations('common');
  const { locale, setLocale } = useLanguage();
  const { stations, selectedStationId, setSelectedStationId, selectedStation } = useForecast();

  const currentStationValue = selectedStationId || 'ST-001';
  const currentTargetValue =
    target !== undefined && target !== ''
      ? target
      : selectedStation?.target_capacity_kw
      ? String(Math.round(selectedStation.target_capacity_kw))
      : '5000';

  return (
    <header className="flex h-16 w-full shrink-0 items-center border-b border-line bg-white shadow-sm">
      <div className="flex h-full w-[64px] shrink-0 items-center justify-center gap-2.5 border-r border-line px-0 md:w-[230px] md:justify-start md:px-5">
        <SunIcon className="h-9 w-9 shrink-0 text-sun" strokeWidth={2.2} />
        <div className="hidden min-w-0 leading-tight md:block">
          <div className="text-[20px] font-bold tracking-tight text-[#1e3a8a]">SolarDSS</div>
          <div className="truncate text-[10px] font-medium text-muted">{t('brand_subtitle')}</div>
        </div>
      </div>

      <div className="flex flex-1 items-center gap-6 px-6">
        <label className="flex items-center gap-3 text-[14px] font-medium text-slate-700">
          <span className="whitespace-nowrap">{t('station_label')}</span>
          <span className="relative">
            <MapPinIcon className="pointer-events-none absolute left-3 top-1/2 h-4.5 w-4.5 -translate-y-1/2 text-brand" />
            <select
              value={currentStationValue}
              onChange={(e) => {
                const newId = e.target.value;
                setSelectedStationId(newId);
                const found = stations.find((s) => s.id === newId);
                if (found) {
                  if (onTargetChange) onTargetChange(String(Math.round(found.target_capacity_kw)));
                }
              }}
              className="h-10 w-[270px] appearance-none rounded-lg border border-line bg-white pl-9 pr-8 text-[13.5px] font-medium text-ink focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft truncate"
            >
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id})
                </option>
              ))}
            </select>
            <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          </span>
        </label>

        <label className="flex items-center gap-3 text-[14px] font-medium text-slate-700">
          <span className="whitespace-nowrap">{t('ptarget_label')}</span>
          <span className="flex h-10 overflow-hidden rounded-lg border border-line focus-within:border-brand-mid focus-within:ring-2 focus-within:ring-brand-soft">
            <input
              value={currentTargetValue}
              onChange={(e) => {
                const cleanVal = e.target.value.replace(/[^0-9]/g, '');
                if (onTargetChange) onTargetChange(cleanVal);
              }}
              inputMode="numeric"
              aria-label="P_target in kW"
              className="w-[110px] px-3 text-[14px] font-medium text-ink focus:outline-none"
            />
            <span className="flex items-center border-l border-line bg-brand-soft px-3 text-[13px] font-semibold text-brand">kW</span>
          </span>
        </label>

        <div className="ml-auto flex items-center gap-4">
          {/* Language Switcher */}
          <div className="flex items-center rounded-lg border border-line bg-slate-50 p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setLocale('th')}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 transition-colors ${
                locale === 'th' ? 'bg-white text-brand shadow-sm font-bold' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              TH
            </button>
            <button
              type="button"
              onClick={() => setLocale('en')}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 transition-colors ${
                locale === 'en' ? 'bg-white text-brand shadow-sm font-bold' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              EN
            </button>
          </div>

          <span className="h-7 w-px bg-line" />

          {/* User Profile Popover - Streamlined to Profile, Settings, Login */}
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function UserMenu() {
  const t = useTranslations('common');
  const router = useRouter();
  const { user, isLoggedIn, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside or pressing Escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleLogout = () => {
    logout();
    setIsOpen(false);
  };

  const displayName = isLoggedIn ? user?.name || 'ทวีพร ช่วยบำรุง' : t('guest_user');
  const displayRole = isLoggedIn ? user?.role || t('menu_free_tier') : t('menu_guest_tier');

  // Generate initials for avatar (e.g. TA or GO)
  const getInitials = (name: string) => {
    if (!isLoggedIn) return 'GU';
    if (name.includes('ทวีพร')) return 'TA';
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return name.slice(0, 2).toUpperCase();
  };

  const initials = getInitials(displayName);

  return (
    <div className="relative" ref={menuRef}>
      {/* Trigger Button - Styled identically to bottom profile container */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2.5 rounded-2xl bg-slate-100/90 py-1 pl-1.5 pr-3 text-left transition-all hover:bg-slate-200/70 ${
          isOpen ? 'ring-2 ring-slate-300' : ''
        }`}
      >
        <span
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-bold text-xs text-white shadow-xs ${
            isLoggedIn ? 'bg-[#e065a3]' : 'bg-slate-400'
          }`}
        >
          {initials}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-bold leading-tight text-slate-800">
            {displayName}
          </p>
          <p className="truncate text-[11px] font-medium leading-tight text-slate-400">
            {displayRole}
          </p>
        </div>
        <ChevronDownIcon
          className={`ml-1 h-3.5 w-3.5 text-slate-400 transition-transform duration-200 ${
            isOpen ? 'rotate-180 text-slate-600' : ''
          }`}
        />
      </button>

      {/* Popover Card - Streamlined to Profile, Setting, and Login/Logout */}
      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-2 w-64 origin-top-right rounded-2xl border border-slate-200/90 bg-white p-1.5 shadow-2xl animate-in fade-in zoom-in-95">
          {/* Header Row */}
          <div
            onClick={() => {
              if (!isLoggedIn) {
                router.push('/login');
              } else {
                alert(`โปรไฟล์ผู้ใช้:\nชื่อ: ${displayName}\nอีเมล: ${user?.email || 'operator@solardss.io'}\nบทบาท: ${displayRole}`);
              }
              setIsOpen(false);
            }}
            className="flex items-center gap-3 rounded-xl p-2.5 transition-colors hover:bg-slate-50 cursor-pointer"
          >
            <span
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-bold text-xs text-white shadow-xs ${
                isLoggedIn ? 'bg-[#e065a3]' : 'bg-slate-400'
              }`}
            >
              {initials}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13.5px] font-semibold text-slate-900 leading-tight">
                {displayName}
              </p>
              <p className="truncate text-[11.5px] font-medium text-slate-400 leading-tight">
                {displayRole}
              </p>
            </div>
            <ChevronRightIcon className="h-4 w-4 text-slate-400 ml-auto shrink-0" />
          </div>

          <div className="my-1 border-t border-slate-100" />

          {/* Menu Items - Only Profile and Settings */}
          <div className="flex flex-col gap-0.5">
            <button
              type="button"
              onClick={() => {
                if (isLoggedIn) {
                  alert(`โปรไฟล์ผู้ใช้:\nชื่อ: ${displayName}\nอีเมล: ${user?.email || 'operator@solardss.io'}\nบทบาท: ${displayRole}`);
                } else {
                  router.push('/login');
                }
                setIsOpen(false);
              }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] font-medium text-slate-700 transition-colors hover:bg-slate-50 text-left"
            >
              <UserIcon className="h-4.5 w-4.5 text-slate-700 shrink-0" />
              <span>{t('menu_profile')}</span>
            </button>

            <button
              type="button"
              onClick={() => {
                alert('การตั้งค่าระบบ (Settings):\n- ภาษา: ภาษาไทย / English\n- ระบบพยากรณ์: Real-time Sync\n- โหมดแจ้งเตือน: On');
                setIsOpen(false);
              }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] font-medium text-slate-700 transition-colors hover:bg-slate-50 text-left"
            >
              <SettingsIcon className="h-4.5 w-4.5 text-slate-700 shrink-0" />
              <span>{t('menu_settings')}</span>
            </button>
          </div>

          <div className="my-1 border-t border-slate-100" />

          {/* Login / Logout Action */}
          <div className="flex flex-col gap-0.5">
            {isLoggedIn ? (
              <button
                type="button"
                onClick={handleLogout}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] font-medium text-slate-700 transition-colors hover:bg-slate-50 hover:text-red-600 text-left"
              >
                <LogOutIcon className="h-4.5 w-4.5 text-slate-700 shrink-0" />
                <span>{t('menu_logout')}</span>
              </button>
            ) : (
              <Link
                href="/login"
                onClick={() => setIsOpen(false)}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] font-semibold text-brand transition-colors hover:bg-brand-soft/60"
              >
                <LogInIcon className="h-4.5 w-4.5 text-brand shrink-0" />
                <span>{t('menu_login')}</span>
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}