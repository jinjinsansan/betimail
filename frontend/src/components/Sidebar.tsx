"use client";
import { I } from "@/lib/icons";
import type { Health } from "@/lib/types";
import type { ReactNode } from "react";

export type TabKey =
  | "dashboard"
  | "send"
  | "approvals"
  | "members"
  | "history"
  | "withdraws"
  | "afi-withdraws"
  | "lucky"
  | "portal"
  | "templates"
  | "jobs";

type Item = { key: TabKey; label: string; icon: ReactNode; badge?: number };

type Props = {
  current: TabKey;
  onNavigate: (key: TabKey) => void;
  approvalCount: number;
  health: Health | null;
  username: string;
  onLogout: () => void;
};

export default function Sidebar({ current, onNavigate, approvalCount, health, username, onLogout }: Props) {
  const items: Item[] = [
    { key: "dashboard", label: "ダッシュボード", icon: <I.Home /> },
    { key: "send", label: "メール送信", icon: <I.Send /> },
    { key: "approvals", label: "承認待ち", icon: <I.Clock />, badge: approvalCount },
    { key: "members", label: "メンバー管理", icon: <I.Users /> },
    { key: "history", label: "送受信履歴", icon: <I.Inbox /> },
    { key: "withdraws", label: "買い取り出金", icon: <I.DollarSign /> },
    { key: "afi-withdraws", label: "アフィリエイト出金", icon: <I.DollarSign /> },
    { key: "lucky", label: "ラッキー報酬", icon: <I.Sparkle /> },
    { key: "portal", label: "ポータル管理", icon: <I.Shield /> },
    { key: "templates", label: "テンプレート", icon: <I.FileText /> },
    { key: "jobs", label: "送信ジョブ", icon: <I.Truck /> },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">B</div>
        <div>
          <div className="brand-name">Betimail</div>
          <div className="brand-sub">NFT support inbox</div>
        </div>
      </div>

      <div className="nav-section">ワークスペース</div>
      <NavItem item={items[0]} active={current === items[0].key} onClick={() => onNavigate(items[0].key)} />

      <div className="nav-section">メール</div>
      {items.slice(1, 5).map((it) => (
        <NavItem key={it.key} item={it} active={current === it.key} onClick={() => onNavigate(it.key)} />
      ))}

      <div className="nav-section">買い取り・報酬</div>
      {items.slice(5, 9).map((it) => (
        <NavItem key={it.key} item={it} active={current === it.key} onClick={() => onNavigate(it.key)} />
      ))}

      <div className="nav-section">設定</div>
      {items.slice(9).map((it) => (
        <NavItem key={it.key} item={it} active={current === it.key} onClick={() => onNavigate(it.key)} />
      ))}

      <div className="sidebar-footer">
        {health && (
          <>
            <div className="status-pill">
              <span className={`status-dot ${health.admin_auth_enabled ? "ok" : "warn"}`} />
              {health.admin_auth_enabled ? "認証ON" : "認証OFF"}
            </div>
            <div className="status-pill">
              <span className={`status-dot ${health.telegram_enabled ? "ok" : "off"}`} />
              Telegram {health.telegram_enabled ? "連携中" : "未設定"}
            </div>
          </>
        )}
        <div className="user-chip" onClick={onLogout} title="ログアウト">
          <div className="avatar">{(username[0] || "?").toUpperCase()}</div>
          <div style={{ overflow: "hidden", flex: 1 }}>
            <div className="user-name">{username}</div>
            <div className="user-mail">クリックでログアウト</div>
          </div>
          <I.LogOut size={14} />
        </div>
      </div>
    </aside>
  );
}

function NavItem({ item, active, onClick }: { item: Item; active: boolean; onClick: () => void }) {
  return (
    <div className={`nav-item ${active ? "active" : ""}`} onClick={onClick}>
      {item.icon}
      <span>{item.label}</span>
      {item.badge != null && item.badge > 0 && <span className="nav-badge">{item.badge}</span>}
    </div>
  );
}
