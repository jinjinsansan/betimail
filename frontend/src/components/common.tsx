"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import type { CSSProperties, ReactNode } from "react";
import { I } from "@/lib/icons";

// ── Toast ──────────────────────────────────────────────
export type ToastType = "success" | "error" | "info";
export type ToastItem = { id: number; msg: string; type: ToastType };

export function Toast({ msg, type, onClose }: { msg: string; type: ToastType; onClose: () => void }) {
  useEffect(() => {
    const h = setTimeout(onClose, 3200);
    return () => clearTimeout(h);
  }, [onClose]);
  return (
    <div className={`toast ${type}`}>
      {type === "success" ? <I.CheckCircle /> : type === "error" ? <I.XCircle /> : <I.Info />}
      <span>{msg}</span>
    </div>
  );
}

export function ToastStack({ toasts, dismiss }: { toasts: ToastItem[]; dismiss: (id: number) => void }) {
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <Toast key={t.id} msg={t.msg} type={t.type} onClose={() => dismiss(t.id)} />
      ))}
    </div>
  );
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);
  const notify = useCallback((msg: string, type: ToastType = "success") => {
    const id = ++idRef.current;
    setToasts((ts) => [...ts, { id, msg, type }]);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  return { toasts, notify, dismiss };
}

// ── Modal ──────────────────────────────────────────────
export function Modal({
  open, onClose, title, children, footer, width,
}: {
  open: boolean; onClose: () => void; title: string;
  children: ReactNode; footer?: ReactNode; width?: number;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        style={width ? { maxWidth: width } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" style={{ marginLeft: "auto" }} onClick={onClose} aria-label="Close">
            <I.X />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

// ── Pager ──────────────────────────────────────────────
export function Pager({ page, pageCount, onChange }: { page: number; pageCount: number; onChange: (p: number) => void }) {
  if (pageCount <= 1) return null;
  return (
    <div className="pager">
      <button className="btn ghost sm" disabled={page === 0} onClick={() => onChange(page - 1)}>
        <I.ChevronLeft />
      </button>
      <span style={{ fontSize: 12, color: "var(--text-3)", padding: "0 8px", minWidth: 60, textAlign: "center" }}>
        {page + 1} / {pageCount}
      </span>
      <button className="btn ghost sm" disabled={page >= pageCount - 1} onClick={() => onChange(page + 1)}>
        <I.ChevronRight />
      </button>
    </div>
  );
}

// ── ConfBar ────────────────────────────────────────────
export function ConfBar({ value }: { value?: number | null }) {
  const v = value || 0;
  const pct = Math.round(v * 100);
  const cls = pct < 50 ? "danger" : pct < 75 ? "warn" : "";
  return (
    <div className="conf-bar">
      <div className="conf-track">
        <div className={`conf-fill ${cls}`} style={{ width: pct + "%" }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{pct}%</span>
    </div>
  );
}

// ── Empty ──────────────────────────────────────────────
export function Empty({ icon, title, sub }: { icon: ReactNode; title: string; sub?: string }) {
  return (
    <div className="empty">
      {icon}
      <div style={{ fontWeight: 500, color: "var(--text-2)", marginBottom: 4, marginTop: 6 }}>{title}</div>
      {sub && <div>{sub}</div>}
    </div>
  );
}

// ── StatCard ───────────────────────────────────────────
export function StatCard({
  label, value, delta, deltaUp, deltaDown, icon, danger, onClick,
}: {
  label: string; value: number | string; delta?: string;
  deltaUp?: boolean; deltaDown?: boolean; icon?: ReactNode; danger?: boolean; onClick?: () => void;
}) {
  return (
    <div className="stat" onClick={onClick} style={onClick ? { cursor: "pointer" } : undefined}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="stat-label">{label}</div>
        <span style={{ color: danger ? "var(--danger)" : "var(--text-4)" }}>{icon}</span>
      </div>
      <div className="stat-value" style={danger ? { color: "var(--danger)" } : undefined}>{value}</div>
      {delta && (
        <div className={`stat-delta ${deltaUp ? "up" : deltaDown ? "down" : ""}`}>{delta}</div>
      )}
    </div>
  );
}
