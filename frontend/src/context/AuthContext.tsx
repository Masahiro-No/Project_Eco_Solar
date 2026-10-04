"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { API_BASE_URL, DEMO_MODE } from '@/lib/config';

export type User = {
  id?: number;
  name: string;
  email: string;
  role: string;
  avatar?: string;
};

type AuthContextType = {
  user: User | null;
  token: string | null;
  isLoggedIn: boolean;
  isLoading: boolean;
  login: (email?: string, password?: string, name?: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  isLoggedIn: false,
  isLoading: false,
  login: async () => ({ success: false }),
  logout: () => {},
});

const DEFAULT_ROLE = 'Chief Dispatcher';

// Only used when NEXT_PUBLIC_DEMO_MODE=true
const DEMO_OPERATOR: User = {
  name: 'Grid Operator',
  email: 'operator@solardss.io',
  role: DEFAULT_ROLE,
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  // true until the stored session has been read, so route guards don't redirect too early
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    try {
      const savedUser = localStorage.getItem('solar_user');
      const savedToken = localStorage.getItem('solar_token');
      if (savedToken) setToken(savedToken);
      if (savedUser) setUser(JSON.parse(savedUser));
    } catch {
      setUser(null);
    }
    setIsLoading(false);
  }, []);

  const persistUser = (u: User) => {
    setUser(u);
    localStorage.setItem('solar_user', JSON.stringify(u));
  };

  const demoLogin = (email: string, customName?: string): { success: boolean } => {
    persistUser({
      name: customName || (email.includes('@') ? email.split('@')[0] : email) || DEMO_OPERATOR.name,
      email: email.includes('@') ? email : DEMO_OPERATOR.email,
      role: DEFAULT_ROLE,
    });
    return { success: true };
  };

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
          if (DEMO_MODE && targetEmail === DEMO_OPERATOR.email) {
            return demoLogin(targetEmail, customName);
          }
          return { success: false, error: typeof detail === 'string' ? detail : 'Invalid email or password' };
        }

        const data = await response.json();
        const accessToken: string = data.access_token;
        setToken(accessToken);
        localStorage.setItem('solar_token', accessToken);

        let loggedUser: User = {
          name: customName || targetEmail.split('@')[0],
          email: targetEmail,
          role: DEFAULT_ROLE,
        };
        try {
          const meRes = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (meRes.ok) {
            const me = await meRes.json();
            loggedUser = {
              id: me.id,
              name: customName || String(me.email).split('@')[0].replace(/[._]/g, ' '),
              email: me.email,
              role: DEFAULT_ROLE,
            };
          }
        } catch (meErr) {
          console.warn('Could not fetch /api/auth/me, using fallback profile', meErr);
        }
        persistUser(loggedUser);
        return { success: true };
      } catch {
        // Backend unreachable
        if (DEMO_MODE) {
          console.info('[Auth] API unreachable, using offline demo mode.');
          return demoLogin(targetEmail, customName);
        }
        return { success: false, error: 'Cannot reach the server. Please try again later.' };
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('solar_user');
    localStorage.removeItem('solar_token');
  }, []);

  const value = useMemo(
    () => ({ user, token, isLoggedIn: !!user, isLoading, login, logout }),
    [user, token, isLoading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
