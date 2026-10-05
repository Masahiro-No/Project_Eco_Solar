"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { API_BASE_URL } from '@/lib/config';
import { UNAUTHORIZED_EVENT } from '@/services/api';

export type UserRole = 'operator' | 'admin';

export type User = {
  id?: number;
  name: string;
  email: string;
  /** operator = read forecasts and decisions; admin = also label data and manage stations */
  role: UserRole;
  avatar?: string;
};

export type RegisterResult = { success: boolean; error?: string; code?: 'exists' | 'invalid' | 'network' };

type AuthContextType = {
  user: User | null;
  token: string | null;
  isLoggedIn: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  login: (email?: string, password?: string, name?: string) => Promise<{ success: boolean; error?: string }>;
  /** Creates an operator account and signs in. Admin rights are given by an admin, never by sign-up. */
  register: (email: string, password: string) => Promise<RegisterResult>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isLoggedIn: false,
  isAdmin: false,
  isLoading: false,
  login: async () => ({ success: false }),
  register: async () => ({ success: false }),
  logout: () => {},
});

/** Expiry time (ms since epoch) of a JWT, or null if it cannot be read. */
function tokenExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function clearStoredSession() {
  localStorage.removeItem('solar_user');
  localStorage.removeItem('solar_token');
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  // true until the stored session has been read, so route guards don't redirect too early
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    clearStoredSession();
  }, []);

  // Restore the stored session only while its token is still valid
  useEffect(() => {
    try {
      const savedUser = localStorage.getItem('solar_user');
      const savedToken = localStorage.getItem('solar_token');
      const expiry = savedToken ? tokenExpiry(savedToken) : null;
      if (savedUser && savedToken && expiry !== null && expiry > Date.now()) {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } else {
        clearStoredSession();
      }
    } catch {
      clearStoredSession();
    }
    setIsLoading(false);
  }, []);

  // End the session when the token expires, or as soon as the backend answers 401
  useEffect(() => {
    if (!token) return;
    const expiry = tokenExpiry(token);
    const timer = expiry !== null ? window.setTimeout(logout, Math.max(0, expiry - Date.now())) : undefined;
    window.addEventListener(UNAUTHORIZED_EVENT, logout);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener(UNAUTHORIZED_EVENT, logout);
    };
  }, [token, logout]);

  const login = useCallback(
    async (email?: string, password?: string, customName?: string): Promise<{ success: boolean; error?: string }> => {
      const targetEmail = (email ?? '').trim();
      const targetPassword = password ?? '';

      if (!targetEmail || !targetPassword) {
        return { success: false, error: 'Invalid email or password' };
      }

      setIsLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: targetEmail, password: targetPassword }),
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => null);
          const detail = errData?.detail || 'Invalid email or password';
          return { success: false, error: typeof detail === 'string' ? detail : 'Invalid email or password' };
        }

        const data = await response.json();
        const accessToken: string = data.access_token;

        // The profile (and the role) always comes from the backend
        const meRes = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!meRes.ok) {
          return { success: false, error: 'Could not load the user profile' };
        }
        const me = await meRes.json();
        const loggedUser: User = {
          id: me.id,
          name: customName || String(me.email).split('@')[0].replace(/[._]/g, ' '),
          email: me.email,
          role: me.role === 'admin' ? 'admin' : 'operator',
        };

        setToken(accessToken);
        setUser(loggedUser);
        localStorage.setItem('solar_token', accessToken);
        localStorage.setItem('solar_user', JSON.stringify(loggedUser));
        return { success: true };
      } catch {
        return { success: false, error: 'Cannot reach the server. Please try again later.' };
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const register = useCallback(
    async (email: string, password: string): Promise<RegisterResult> => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.trim(), password }),
        });
        if (res.status === 409) return { success: false, code: 'exists' };
        if (!res.ok) return { success: false, code: 'invalid' };
      } catch {
        return { success: false, code: 'network' };
      }
      return login(email, password);
    },
    [login]
  );

  const value = useMemo(
    () => ({
      user,
      token,
      isLoggedIn: !!user && !!token,
      isAdmin: user?.role === 'admin',
      isLoading,
      login,
      register,
      logout,
    }),
    [user, token, isLoading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
