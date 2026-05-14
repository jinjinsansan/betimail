"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Paged, SentEmail, ReceivedEmail } from "@/lib/types";
import { nftBadgeClass, nftLabel, statusInfo, fmtDate, debounce } from "@/lib/ui";
import { I } from "@/lib/icons";
import { ConfBar, Empty, Pager } from "../common";

const PAGE = 14;

type Props = {
  notify: (msg: string, type?: "success" | "error" | "info") => void;
};

export default function HistoryTab({ notify }: Props) {
  const [view, setView] = useState<"sent" | "received">("sent");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sent, setSent] = useState<Paged<SentEmail>>({ items: [], total: 0 });
  const [received, setReceived] = useState<Paged<ReceivedEmail>>({ items: [], total: 0 });

  useEffect(() => { setPage(0); }, [view, search, statusFilter]);

  useEffect(() => {
    const load = async () => {
      try {
        if (view === "sent") {
          const r = await api.emails.sent(PAGE, page * PAGE, search);
          setSent(r);
        } else {
          const r = await api.emails.received(PAGE, page * PAGE, search);
          setReceived(r);
        }
      } catch (e: any) { notify(e.message, "error"); }
    };
    load();
  }, [view, page, search]);

  const data = view === "sent" ? sent : received;
  const filteredItems = statusFilter === "all"
    ? data.items
    : data.items.filter((x: any) => x.status === statusFilter);
  const pageCount = Math.ceil(data.total / PAGE);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">送受信履歴</h1>
          <div className="page-sub">送信メールの配送状況と、受信メールの AI 処理結果を確認できます。</div>
        </div>
      </div>

      <div className="card">
        <div className="filter-bar">
          <div className="chip-row">
            <div className={`chip ${view === "sent" ? "active" : ""}`} onClick={() => setView("sent")}>
              送信済 <span className="chip-count">· {sent.total}</span>
            </div>
            <div className={`chip ${view === "received" ? "active" : ""}`} onClick={() => setView("received")}>
              受信 <span className="chip-count">· {received.total}</span>
            </div>
          </div>
          <div style={{ width: 1, height: 20, background: "var(--border)" }} />
          <div className="search-wrap">
            <I.Search />
            <input
              className="input"
              placeholder="件名・名前・メール…"
              defaultValue={search}
              onChange={debounce((e: any) => setSearch(e.target.value), 300)}
            />
          </div>
          <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: 160 }}>
            <option value="all">すべての状態</option>
            <option value="sent">送信済</option>
            <option value="auto_sent">AI自動</option>
            <option value="approved">承認済</option>
            <option value="pending">保留中</option>
            <option value="error">失敗</option>
          </select>
          <span className="count">{filteredItems.length} 件</span>
        </div>

        <div className="tbl-wrap">
          {view === "sent" ? (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>日時</th>
                  <th>宛先</th>
                  <th>NFT</th>
                  <th>件名</th>
                  <th style={{ width: 110 }}>状態</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr><td colSpan={5}><Empty icon={<I.Send />} title="送信履歴がありません" /></td></tr>
                ) : (filteredItems as SentEmail[]).map((e) => {
                  const s = statusInfo(e.status);
                  return (
                    <tr key={e.id}>
                      <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(e.sent_at)}</span></td>
                      <td>
                        <div><b>{e.recipient_name || "(名前なし)"}</b></div>
                        <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{e.recipient_email}</div>
                      </td>
                      <td>{e.nft_type ? <span className={`badge ${nftBadgeClass(e.nft_type)}`}>{nftLabel(e.nft_type)}</span> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                      <td>
                        {e.subject}
                        {e.error && <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 2 }}>{e.error}</div>}
                      </td>
                      <td><span className={`badge ${s.cls} dot`}>{s.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>日時</th>
                  <th>送信者</th>
                  <th>件名</th>
                  <th style={{ width: 130 }}>AI 信頼度</th>
                  <th style={{ width: 110 }}>ステータス</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length === 0 ? (
                  <tr><td colSpan={5}><Empty icon={<I.Inbox />} title="受信履歴がありません" /></td></tr>
                ) : (filteredItems as ReceivedEmail[]).map((e) => {
                  const s = statusInfo(e.status);
                  return (
                    <tr key={e.id}>
                      <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(e.received_at)}</span></td>
                      <td>
                        <div><b>{e.sender_name || "(名前なし)"}</b></div>
                        <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{e.sender_email}</div>
                      </td>
                      <td>{e.subject || "-"}</td>
                      <td>{e.ai_confidence != null ? <ConfBar value={e.ai_confidence} /> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                      <td><span className={`badge ${s.cls} dot`}>{s.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 12, color: "var(--text-3)" }}>
            {data.total === 0 ? 0 : page * PAGE + 1}–{Math.min((page + 1) * PAGE, data.total)} / {data.total}
          </span>
          <Pager page={page} pageCount={pageCount} onChange={setPage} />
        </div>
      </div>
    </>
  );
}
