"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SentEmail, ReceivedEmail, Paged } from "@/lib/types";
import { fmtDate, statusBadge, nftBadgeClass, debounce } from "@/lib/ui";

const PAGE_SIZE = 25;

type Props = {
  notify: (msg: string, err?: boolean) => void;
};

export default function HistoryTab({ notify }: Props) {
  const [sent, setSent] = useState<Paged<SentEmail>>({ items: [], total: 0 });
  const [received, setReceived] = useState<Paged<ReceivedEmail>>({ items: [], total: 0 });
  const [sentPage, setSentPage] = useState(0);
  const [receivedPage, setReceivedPage] = useState(0);
  const [sentSearch, setSentSearch] = useState("");
  const [receivedSearch, setReceivedSearch] = useState("");

  async function loadSent(page: number, search: string) {
    try {
      const r = await api.emails.sent(PAGE_SIZE, page * PAGE_SIZE, search);
      setSent(r);
    } catch (e: any) { notify(e.message, true); }
  }
  async function loadReceived(page: number, search: string) {
    try {
      const r = await api.emails.received(PAGE_SIZE, page * PAGE_SIZE, search);
      setReceived(r);
    } catch (e: any) { notify(e.message, true); }
  }

  useEffect(() => { loadSent(sentPage, sentSearch); }, [sentPage, sentSearch]);
  useEffect(() => { loadReceived(receivedPage, receivedSearch); }, [receivedPage, receivedSearch]);

  const sentTotal = Math.ceil(sent.total / PAGE_SIZE);
  const recvTotal = Math.ceil(received.total / PAGE_SIZE);

  return (
    <>
      <div className="card">
        <h2>送信済みメール
          <div className="actions">
            <input
              placeholder="検索"
              style={{ width: 200, padding: "6px 10px" }}
              onChange={debounce((e: any) => { setSentSearch(e.target.value); setSentPage(0); }, 300)}
            />
          </div>
        </h2>
        <table>
          <thead><tr><th>日時</th><th>宛先</th><th>NFT種別</th><th>件名</th><th>状態</th></tr></thead>
          <tbody>
            {sent.items.length === 0 ? (
              <tr><td colSpan={5} className="placeholder">送信履歴なし</td></tr>
            ) : sent.items.map((e) => {
              const sb = statusBadge(e.status);
              return (
                <tr key={e.id}>
                  <td>{fmtDate(e.sent_at)}</td>
                  <td>{e.recipient_name || ""} <span style={{ color: "#666" }}>&lt;{e.recipient_email}&gt;</span></td>
                  <td><span className={`badge ${nftBadgeClass(e.nft_type)}`}>{e.nft_type || "不明"}</span></td>
                  <td>{e.subject}</td>
                  <td>
                    <span className={`status-dot ${sb.dot}`}></span>{sb.text}
                    {e.error && <div className="hint">{e.error}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {sentTotal > 1 && (
          <div className="pager">
            <button disabled={sentPage === 0} onClick={() => setSentPage((p) => p - 1)}>←</button>
            <span style={{ color: "var(--text-dim)" }}>{sentPage + 1} / {sentTotal}</span>
            <button disabled={sentPage >= sentTotal - 1} onClick={() => setSentPage((p) => p + 1)}>→</button>
          </div>
        )}
      </div>

      <div className="card">
        <h2>受信メール（AI処理状況）
          <div className="actions">
            <input
              placeholder="検索"
              style={{ width: 200, padding: "6px 10px" }}
              onChange={debounce((e: any) => { setReceivedSearch(e.target.value); setReceivedPage(0); }, 300)}
            />
          </div>
        </h2>
        <table>
          <thead><tr><th>日時</th><th>送信者</th><th>件名</th><th>AI信頼度</th><th>ステータス</th></tr></thead>
          <tbody>
            {received.items.length === 0 ? (
              <tr><td colSpan={5} className="placeholder">受信履歴なし</td></tr>
            ) : received.items.map((e) => {
              const sb = statusBadge(e.status);
              return (
                <tr key={e.id}>
                  <td>{fmtDate(e.received_at)}</td>
                  <td>{e.sender_name || ""} <span style={{ color: "#666" }}>&lt;{e.sender_email}&gt;</span></td>
                  <td>{e.subject || "-"}</td>
                  <td>{e.ai_confidence != null ? Math.round(e.ai_confidence * 100) + "%" : "-"}</td>
                  <td><span className={`status-dot ${sb.dot}`}></span>{sb.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {recvTotal > 1 && (
          <div className="pager">
            <button disabled={receivedPage === 0} onClick={() => setReceivedPage((p) => p - 1)}>←</button>
            <span style={{ color: "var(--text-dim)" }}>{receivedPage + 1} / {recvTotal}</span>
            <button disabled={receivedPage >= recvTotal - 1} onClick={() => setReceivedPage((p) => p + 1)}>→</button>
          </div>
        )}
      </div>
    </>
  );
}
