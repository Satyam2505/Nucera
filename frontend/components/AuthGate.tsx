"use client";

import { ReactNode } from "react";

import AuthForm from "@/components/AuthForm";
import { AppStateProvider } from "@/lib/AppStateContext";
import { useAuth } from "@/lib/AuthContext";

export default function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user) return <AuthForm />;

  return <AppStateProvider>{children}</AppStateProvider>;
}
