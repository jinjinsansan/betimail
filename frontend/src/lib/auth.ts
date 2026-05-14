const TOKEN_KEY = "betimail_token";
const EXPIRES_KEY = "betimail_token_expires";

export function saveToken(token: string, expiresAt: number) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRES_KEY, String(expiresAt));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(TOKEN_KEY);
  const expires = parseInt(localStorage.getItem(EXPIRES_KEY) || "0", 10);
  if (!token || !expires) return null;
  if (Date.now() / 1000 >= expires) {
    clearToken();
    return null;
  }
  return token;
}

export function clearToken() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}
