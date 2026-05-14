"use client";
import { useEffect, useState } from "react";
import { isAuthenticated } from "@/lib/auth";
import Login from "@/components/Login";
import Dashboard from "@/components/Dashboard";

export default function Home() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  if (authed === null) return null; // SSR/初回ロード時のフリッカー防止

  return authed
    ? <Dashboard onLogout={() => setAuthed(false)} />
    : <Login onSuccess={() => setAuthed(true)} />;
}
