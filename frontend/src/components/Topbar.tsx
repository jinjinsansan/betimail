"use client";
import { I } from "@/lib/icons";

type Props = { trail: string[] };

export default function Topbar({ trail }: Props) {
  return (
    <div className="topbar">
      <div className="crumbs">
        {trail.map((t, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="sep">/</span>}
            {i === trail.length - 1 ? <b>{t}</b> : <span>{t}</span>}
          </span>
        ))}
      </div>
      <div className="topbar-right">
        <button className="icon-btn" title="通知"><I.Bell /></button>
        <button className="icon-btn" title="設定"><I.Settings /></button>
      </div>
    </div>
  );
}
