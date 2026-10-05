/**
 * Central runtime config for the frontend.
 * NEXT_PUBLIC_DEMO_MODE=true enables offline demo behaviours (demo login,
 * mock data fallbacks). It must be off in production builds.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
