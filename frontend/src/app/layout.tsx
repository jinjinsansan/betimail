import "../styles/globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Betimail - NFTコミュニティサポート",
  description: "NFTコミュニティ向けサポートメール管理",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
