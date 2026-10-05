"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  SunIcon,
  MailIcon,
  LockIcon,
  EyeIcon,
  EyeOffIcon,
  ArrowLeftIcon,
  LogInIcon,
  CheckCircle2Icon,
  AlertCircleIcon,
  CpuIcon,
  LineChartIcon,
  ShieldCheckIcon,
  SparklesIcon,
  Building2Icon,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useLanguage } from '@/context/LanguageContext';
import { useAuth } from '@/context/AuthContext';
import { DEMO_MODE } from '@/lib/config';

export default function LoginPage() {
  const t = useTranslations('common');
  const router = useRouter();
  const { locale, setLocale } = useLanguage();
  const { isLoggedIn, login } = useAuth();

  const [activeTab, setActiveTab] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState(DEMO_MODE ? 'operator@solardss.io' : '');
  const [password, setPassword] = useState(DEMO_MODE ? 'operator1234' : '');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // If already logged in, redirect to dashboard
  useEffect(() => {
    if (isLoggedIn && !loading) {
      const timer = setTimeout(() => {
        router.push('/');
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [isLoggedIn, loading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!email || !password) {
      setErrorMsg(t('login_error_invalid'));
      return;
    }

    setLoading(true);
    const result = await login(email, password);
    setLoading(false);

    if (result.success) {
      setSuccessMsg(t('login_success'));
      setTimeout(() => {
        router.push('/');
      }, 800);
    } else {
      setErrorMsg(result.error || t('login_error_invalid'));
    }
  };

  const handleQuickDemo = async () => {
    setEmail('operator@solardss.io');
    setPassword('operator1234');
    setLoading(true);
    const result = await login('operator@solardss.io', 'operator1234', 'Grid Operator');
    setLoading(false);
    if (result.success) {
      setSuccessMsg(t('login_success'));
      setTimeout(() => {
        router.push('/');
      }, 700);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-slate-50 text-slate-800">
      {/* Top Navbar */}
      <header className="flex h-16 w-full items-center justify-between border-b border-line bg-white/80 px-6 backdrop-blur-md">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-semibold text-slate-600 transition-colors hover:text-brand"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          <span>{t('login_back_home')}</span>
        </Link>

        <div className="flex items-center gap-3">
          {/* Sign In button in header */}
          <button
            type="button"
            onClick={() => setActiveTab('signin')}
            className="flex items-center gap-1.5 rounded-lg bg-brand-soft px-3 py-1.5 text-xs font-bold text-brand transition-colors hover:bg-brand-soft/80"
          >
            <LogInIcon className="h-3.5 w-3.5" />
            <span>Sign In</span>
          </button>

          {/* Language Switcher */}
          <div className="flex items-center rounded-lg border border-line bg-slate-50 p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setLocale('th')}
              className={`rounded-md px-2.5 py-1 transition-colors ${
                locale === 'th'
                  ? 'bg-white text-brand shadow-sm font-bold'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              TH
            </button>
            <button
              type="button"
              onClick={() => setLocale('en')}
              className={`rounded-md px-2.5 py-1 transition-colors ${
                locale === 'en'
                  ? 'bg-white text-brand shadow-sm font-bold'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              EN
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex flex-1 items-center justify-center p-4 sm:p-6 lg:p-8">
        <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-line bg-white shadow-xl lg:grid-cols-[1.1fr_1fr]">
          {/* Left Hero Column */}
          <div className="relative hidden flex-col justify-between bg-gradient-to-br from-[#0a163b] via-[#10245e] to-[#1e3a8a] p-8 text-white lg:flex">
            <div>
              {/* Brand */}
              <div className="flex items-center gap-3">
                <SunIcon className="h-10 w-10 text-sun animate-pulse" strokeWidth={2.2} />
                <div>
                  <div className="text-2xl font-bold tracking-tight text-white">SolarDSS</div>
                  <div className="text-xs font-medium text-blue-200">{t('brand_subtitle')}</div>
                </div>
              </div>

              {/* Tagline */}
              <div className="mt-10">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/20 border border-blue-400/30 px-3 py-1 text-xs font-semibold text-blue-200">
                  <SparklesIcon className="h-3.5 w-3.5 text-sun" />
                  AI &amp; Deep Learning DSS
                </span>
                <h2 className="mt-3 text-2xl font-bold leading-tight text-white">
                  Solar Power Forecasting &amp; Decision Support
                </h2>
                <p className="mt-2 text-xs leading-relaxed text-blue-200/90">
                  {t('login_page_subtitle')}
                </p>
              </div>

              {/* Feature Highlights */}
              <div className="mt-8 space-y-3.5 text-xs text-blue-100">
                <div className="flex items-center gap-3 rounded-xl bg-white/5 border border-white/10 p-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/20 text-blue-300">
                    <LineChartIcon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-bold text-white">{t('login_feat_lstm_title')}</p>
                    <p className="text-[11px] text-blue-200/80">{t('login_feat_lstm_desc')}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3 rounded-xl bg-white/5 border border-white/10 p-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
                    <CpuIcon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-bold text-white">{t('login_feat_cloud_title')}</p>
                    <p className="text-[11px] text-blue-200/80">{t('login_feat_cloud_desc')}</p>
                  </div>
                </div>

                <div className="flex items-center gap-3 rounded-xl bg-white/5 border border-white/10 p-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/20 text-amber-300">
                    <ShieldCheckIcon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-bold text-white">{t('login_feat_dss_title')}</p>
                    <p className="text-[11px] text-blue-200/80">{t('login_feat_dss_desc')}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer badge */}
            <div className="mt-8 border-t border-white/10 pt-4 text-[11px] text-blue-300/80 flex items-center justify-between">
              <span>{t('brand_subtitle')}</span>
              <span className="font-mono text-xs">v0.2.0</span>
            </div>
          </div>

          {/* Right Form Column */}
          <div className="flex flex-col justify-center p-8 sm:p-10">
            {/* Header Tabs: Sign In / Sign Up */}
            <div className="mb-6 flex items-center gap-4 border-b border-line pb-2">
              <button
                type="button"
                onClick={() => setActiveTab('signin')}
                className={`flex items-center gap-2 pb-1 text-sm font-bold transition-colors ${
                  activeTab === 'signin'
                    ? 'border-b-2 border-brand text-brand'
                    : 'text-slate-400 hover:text-slate-600'
                }`}
              >
                <LogInIcon className="h-4 w-4" />
                <span>Sign In</span>
              </button>
            </div>

            <div className="mb-5">
              <div className="flex items-center gap-2 lg:hidden mb-3">
                <SunIcon className="h-7 w-7 text-sun" strokeWidth={2.2} />
                <span className="text-xl font-bold tracking-tight text-[#1e3a8a]">SolarDSS</span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-[#0f1f4d]">
                {t('login_welcome_back')}
              </h1>
              <p className="mt-1 text-xs text-slate-500">{t('sign_in_desc')}</p>
            </div>

            {/* Notifications */}
            {errorMsg && (
              <div
                role="alert"
                className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-600"
              >
                <AlertCircleIcon className="h-4 w-4 shrink-0 text-red-500" />
                <span>{errorMsg}</span>
              </div>
            )}

            {successMsg && (
              <div
                role="alert"
                className="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-xs font-semibold text-green-700"
              >
                <CheckCircle2Icon className="h-4 w-4 shrink-0 text-green-600" />
                <span>{successMsg}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                  {t('login_email_label')}
                </label>
                <div className="relative">
                  <MailIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('login_email_placeholder')}
                    required
                    className="h-10 w-full rounded-lg border border-line bg-white pl-9 pr-3 text-sm text-ink placeholder:text-slate-400 focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft"
                  />
                </div>
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="block text-xs font-semibold text-slate-700">
                    {t('login_password_label')}
                  </label>
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      alert('กรุณาติดต่อผู้ดูแลระบบเครือข่ายโครงข่ายไฟฟ้า (Grid Administrator) เพื่อรีเซ็ตรหัสผ่าน');
                    }}
                    className="text-[11px] font-semibold text-brand hover:underline"
                  >
                    {t('login_forgot_password')}
                  </a>
                </div>
                <div className="relative">
                  <LockIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t('login_password_placeholder')}
                    required
                    className="h-10 w-full rounded-lg border border-line bg-white pl-9 pr-10 text-sm text-ink placeholder:text-slate-400 focus:border-brand-mid focus:outline-none focus:ring-2 focus:ring-brand-soft"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-center">
                <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="h-4 w-4 rounded border-line text-brand focus:ring-brand-soft"
                  />
                  <span>{t('login_remember_me')}</span>
                </label>
              </div>

              {/* Main Sign In Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand font-bold text-white shadow-sm transition-colors hover:bg-brand/90 disabled:opacity-50"
              >
                {loading ? (
                  <span className="flex items-center gap-2 text-sm">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    {t('login_btn_loading')}
                  </span>
                ) : (
                  <>
                    <LogInIcon className="h-4 w-4" />
                    <span>{t('login_btn_submit')}</span>
                  </>
                )}
              </button>
            </form>

            {/* Quick Demo Section (demo mode only) */}
            {DEMO_MODE && (
            <div className="mt-5 border-t border-line pt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11.5px] font-semibold text-slate-500">
                  {t('login_demo_badge')}
                </span>
                <span className="rounded bg-ok-soft px-2 py-0.5 text-[10.5px] font-bold text-ok">
                  Ready to test
                </span>
              </div>
              <p className="text-[11px] text-muted mb-2.5 leading-tight">
                {t('login_demo_hint')}
              </p>

              <div className="flex flex-col gap-2">
                {/* Sign In as Grid Operator Demo Button */}
                <button
                  type="button"
                  onClick={handleQuickDemo}
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-brand/30 bg-brand-soft px-3 py-2 text-xs font-bold text-brand transition-colors hover:bg-brand-soft/80"
                >
                  <SparklesIcon className="h-3.5 w-3.5 text-brand" />
                  <span>{t('login_quick_btn')}</span>
                </button>

                {/* Sign In with Enterprise SSO Button */}
                <button
                  type="button"
                  disabled
                  title="SSO is not configured yet"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                >
                  <Building2Icon className="h-3.5 w-3.5 text-slate-500" />
                  <span>Sign In with Enterprise SSO</span>
                </button>
              </div>
            </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
