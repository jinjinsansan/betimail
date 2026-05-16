"use client";
import { Fragment, useEffect, useState } from "react";
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
  const [bulkFilter, setBulkFilter] = useState<"exclude" | "include" | "only">("exclude");
  const [sent, setSent] = useState<Paged<SentEmail>>({ items: [], total: 0 });
  const [received, setReceived] = useState<Paged<ReceivedEmail>>({ items: [], total: 0 });
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => { setPage(0); setExpanded(null); }, [view, search, statusFilter, bulkFilter]);

  useEffect(() => {
    const load = async () => {
      try {
        if (view === "sent") {
          const r = await api.emails.sent(PAGE, page * PAGE, search, bulkFilter);
          setSent(r);
        } else {
          const r = await api.emails.received(PAGE, page * PAGE, search);
          setReceived(r);
        }
      } catch (e: any) { notify(e.message, "error"); }
    };
    load();
  }, [view, page, search, bulkFilter]);

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
          {view === "sent" && (
            <select
              className="select"
              value={bulkFilter}
              onChange={(e) => setBulkFilter(e.target.value as "exclude" | "include" | "only")}
              style={{ width: 180 }}
              title="メルマガ一斉送信の表示制御"
            >
              <option value="exclude">個別のみ（メルマガ非表示）</option>
              <option value="include">メルマガも含む</option>
              <option value="only">メルマガのみ</option>
            </select>
          )}
          <span className="count">{filteredItems.length} 件</span>
        </div>

        <div className="tbl-wrap">
          {view === "sent" ? (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>日時 (JST)</th>
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
                  const key = `sent-${e.id}`;
                  const isOpen = expanded === key;
                  return (
                    <Fragment key={key}>
                      <tr onClick={() => setExpanded(isOpen ? null : key)} style={{ cursor: "pointer" }}>
                        <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(e.sent_at)}</span></td>
                        <td>
                          <div><b>{e.recipient_name || "(名前なし)"}</b></div>
                          <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{e.recipient_email}</div>
                        </td>
                        <td>{e.nft_type ? <span className={`badge ${nftBadgeClass(e.nft_type)}`}>{nftLabel(e.nft_type)}</span> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <I.ChevronDown size={14} style={{ color: "var(--text-3)", transform: isOpen ? "rotate(180deg)" : "none", transition: "transform .15s", flex: "0 0 14px" }} />
                            <span>{e.subject}</span>
                            {e.bulk_job_id && (
                              <span className="badge badge-info" title={`ジョブ #${e.bulk_job_id}`}>
                                メルマガ #{e.bulk_job_id}
                              </span>
                            )}
                          </div>
                          {e.error && <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 2 }}>{e.error}</div>}
                        </td>
                        <td><span className={`badge ${s.cls} dot`}>{s.label}</span></td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={5} style={{ background: "var(--bg-soft)", padding: "16px 20px" }}>
                            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 6, fontWeight: 500 }}>
                              <I.Send size={11} /> 送信本文
                            </div>
                            <div className="preview-box" style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.7, background: "var(--bg-elev)" }}>
                              {e.body || "(本文なし)"}
                            </div>
                            {e.resend_id && (
                              <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
                                Resend ID: {e.resend_id}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 140 }}>日時 (JST)</th>
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
                  const key = `received-${e.id}`;
                  const isOpen = expanded === key;
                  return (
                    <Fragment key={key}>
                      <tr onClick={() => setExpanded(isOpen ? null : key)} style={{ cursor: "pointer" }}>
                        <td><span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-3)" }}>{fmtDate(e.received_at)}</span></td>
                        <td>
                          <div><b>{e.sender_name || "(名前なし)"}</b></div>
                          <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>{e.sender_email}</div>
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <I.ChevronDown size={14} style={{ color: "var(--text-3)", transform: isOpen ? "rotate(180deg)" : "none", transition: "transform .15s", flex: "0 0 14px" }} />
                            <span>{e.subject || "(件名なし)"}</span>
                          </div>
                        </td>
                        <td>{e.ai_confidence != null ? <ConfBar value={e.ai_confidence} /> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                        <td><span className={`badge ${s.cls} dot`}>{s.label}</span></td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={5} style={{ background: "var(--bg-soft)", padding: "16px 20px" }}>
                            <div style={{ fontSize: 12, color: "var(--text-3)", marginBottom: 6, fontWeight: 500 }}>
                              <I.Inbox size={11} /> 受信本文
                            </div>
                            <div className="preview-box" style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.7, background: "var(--bg-elev)" }}>
                              {e.body || "(本文なし)"}
                            </div>
                            {e.ai_draft && (
                              <>
                                <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 14, marginBottom: 6, fontWeight: 500 }}>
                                  <I.Sparkle size={11} /> AI 下書き
                                </div>
                                <div className="preview-box" style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.7, background: "var(--bg-elev)", borderColor: "rgba(91,91,214,.25)" }}>
                                  {e.ai_draft}
                                </div>
                              </>
                            )}
                            {e.message_id && (
                              <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-4)", fontFamily: "var(--font-mono)" }}>
                                Message-ID: {e.message_id}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
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
