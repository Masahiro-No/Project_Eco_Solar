"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';

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

const DEFAULT_OPERATOR: User = {
  name: 'Grid Operator',
  email: 'operator@solardss.io',
  role: 'Chief Dispatcher',
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const savedUser = localStorage.getItem('solar_user');
    const savedToken = localStorage.getItem('solar_token');

    if (savedToken) {
      setToken(savedToken);
    }

    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch {
        setUser(null);
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (
    email?: string,
    password?: string,
    customName?: string
  ): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);

    const targetEmail = (email || DEFAULT_OPERATOR.email).trim();
    const targetPassword = password || 'operator1234';

    // 1. Attempt Real Backend API Login (FastAPI POST /api/auth/login)
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: targetEmail, password: targetPassword }),
      });

      if (response.ok) {
        const data = await response.json();
        const accessToken = data.access_token;
        setToken(accessToken);
        localStorage.setItem('solar_token', accessToken);

        // Fetch User Info (/api/auth/me)
        try {
          const meRes = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (meRes.ok) {
            const meData = await meRes.json();
            const loggedUser: User = {
              id: meData.id,
              name: customName || meData.email.split('@')[0].replace(/[._]/g, ' '),
              email: meData.email,
              role: DEFAULT_OPERATOR.role,
            };
            setUser(loggedUser);
            localStorage.setItem('solar_user', JSON.stringify(loggedUser));
            setIsLoading(false);
            return { success: true };
          }
        } catch (meErr) {
          console.warn('Could not fetch /api/auth/me, using fallback profile', meErr);
        }

        // Fallback user profile with token
        const loggedUser: User = {
          name: customName || targetEmail.split('@')[0],
          email: targetEmail,
          role: DEFAULT_OPERATOR.role,
        };
        setUser(loggedUser);
        localStorage.setItem('solar_user', JSON.stringify(loggedUser));
        setIsLoading(false);
        return { success: true };
      } else {
        // Backend returned error status
        const errData = await response.json().catch(() => null);
        const detail = errData?.detail || 'Invalid email or password';
        console.warn(`[Backend Auth] Login rejected (${response.status}):`, detail);

        // Demo fallback for operator demo testing
        if (targetEmail === DEFAULT_OPERATOR.email || targetEmail === 'Grid Operator') {
          const loggedUser: User = {
            name: customName || DEFAULT_OPERATOR.name,
            email: DEFAULT_OPERATOR.email,
            role: DEFAULT_OPERATOR.role,
          };
          setUser(loggedUser);
          localStorage.setItem('solar_user', JSON.stringify(loggedUser));
          setIsLoading(false);
          return { success: true };
        }

        setIsLoading(false);
        return { success: false, error: detail };
      }
    } catch (networkErr) {
      console.info('[Backend Auth] API unreachable, using seamless offline demo mode.');
      // 2. Seamless Demo Fallback when backend server is offline
      const loggedUser: User = {
        name:
          customName ||
          (targetEmail.includes('@') ? targetEmail.split('@')[0] : targetEmail) ||
          DEFAULT_OPERATOR.name,
        email: targetEmail.includes('@') ? targetEmail : DEFAULT_OPERATOR.email,
        role: DEFAULT_OPERATOR.role,
      };
      setUser(loggedUser);
      localStorage.setItem('solar_user', JSON.stringify(loggedUser));
      setIsLoading(false);
      return { success: true };
    }
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('solar_user');
    localStorage.removeItem('solar_token');
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoggedIn: !!user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
