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
  status: string;
  created_at: string;
  finished_at?: string;
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
