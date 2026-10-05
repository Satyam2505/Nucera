"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { api, setSessionExpiredHandler, User } from "./api";
import { clearToken, getToken, setToken } from "./token";

interface AuthState {
  user: User | null;
  loading: boolean;
  // True after a request was rejected for an expired or invalid token, so the
  // login form can say why the user is back there.
  sessionExpired: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  // api.ts has already cleared the token by the time this runs; dropping the
  // user is what sends the app back to the login form. Registered before the
  // startup check below so a stale token found there is handled the same way.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null);
      setSessionExpired(true);
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      // A 401 already signed out centrally (and cleared the token). Any other
      // failure, such as the backend being down, keeps the token so a reload
      // can retry instead of forgetting a perfectly good session.
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    setToken(access_token);
    const me = await api.me();
    setSessionExpired(false);
    setUser(me);
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      await api.register(email, password);
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    clearToken();
    setSessionExpired(false);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, sessionExpired, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
