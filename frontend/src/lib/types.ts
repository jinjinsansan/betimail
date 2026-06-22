export type Member = {
  name: string;
  email: string;
  nft_type: string;
  joined_date: string;
  notes: string;
};

export type SentEmail = {
  id: number;
  recipient_email: string;
  recipient_name: string;
  nft_type: string;
  subject: string;
  body: string;
  sent_at: string;
  resend_id?: string;
  bulk_job_id?: number;
  status: string;
  error?: string;
};

export type ReceivedEmail = {
  id: number;
  sender_email: string;
  sender_name: string;
  subject: string;
  body: string;
  received_at: string;
  status: string;
  ai_draft?: string;
  ai_confidence?: number;
  message_id?: string;
};

export type Approval = {
  id: number;
  received_email_id: number;
  ai_draft: string;
  created_at: string;
  status: string;
  sender_email: string;
  sender_name: string;
  original_subject: string;
  original_body: string;
  ai_confidence?: number | null;
  original_message_id?: string | null;
  telegram_message_id?: number | null;
};

export type Template = {
  id: number;
  name: string;
  subject: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type BulkJob = {
  id: number;
  subject: string;
  body: string;
  nft_types: string;
  total: number;
  sent: number;
  failed: number;
  status: string;  // running | scheduled | done | cancelled | error
  created_at: string;
  finished_at?: string;
  scheduled_at?: string | null;
  segment?: string | null;
  confirm_all?: number;
};

export type Health = {
  status: string;
  admin_auth_enabled: boolean;
  telegram_enabled: boolean;
  version: string;
};

export type LoginResponse = {
  token: string;
  expires_at: number;
  username: string;
};

export type Paged<T> = {
  items: T[];
  total: number;
};

export type MemberHistory = {
  member: Member;
  sent: SentEmail[];
  received: ReceivedEmail[];
};

export type Purchase = {
  id: number;
  email: string;
  name: string;
  nft_type: string;
  amount_jpy?: number | null;
  units?: number | null;
  team?: string;
  transaction_id?: string;
  purchased_at?: string;
  status?: string;
  returns_usdt?: number | null;
  notes?: string;
  imported_at?: string;
  source_file?: string;
};

export type PurchaseSummaryRow = {
  nft_type: string;
  total_jpy?: number | null;
  total_units?: number | null;
  total_returns_usdt?: number | null;
  first_purchase?: string;
  purchase_count: number;
};

export type PurchaseSummary = {
  email: string;
  by_nft: PurchaseSummaryRow[];
  total_count: number;
  total_jpy: number;
  total_returns_usdt: number;
};

export type MemberPurchases = {
  member: Member;
  purchases: Purchase[];
  summary: PurchaseSummary;
};

export type WithdrawRequest = {
  id: number;
  external_id: number;
  source?: string;  // 'nftportal' (ポータル/買い取り) | 'afi' (アフィリエイト)
  email: string;
  name: string;
  user_id?: number | null;
  amount_usdt: number;
  destination?: string | null;
  type?: number | null;
  status?: number | null;
  requested_at?: string | null;
  action_at?: string | null;
  secret_code?: string | null;
  packet?: string | null;
  title?: string | null;
  nft_kind?: string | null;
  raw_json?: string | null;
  imported_at?: string;
  notified_at?: string | null;
};

export type WithdrawsList = {
  items: WithdrawRequest[];
  total_count: number;
  total_usdt: number;
  by_recipient: { email: string; name: string; count: number; total_usdt: number }[];
};

export type WithdrawStats = {
  count: number;
  total_usdt: number;
  unique_recipients: number;
};

export type MemberWithdrawSummary = {
  email: string;
  count: number;
  total_usdt: number;
  withdraws: WithdrawRequest[];
};

export type LuckyDistribution = {
  id: number;
  nft: string;
  distributed_for: string | null;
  pool_amount: number;
  total_nft: number;
  rate: number | null;
  recipients: number;
  status: string;
  created_by: string;
  created_at: string;
};

export type LuckyAdminSummary = {
  totals: { members: number; total_nft: number; total_balance: number; total_reward: number };
  latest_distribution: LuckyDistribution | null;
};
