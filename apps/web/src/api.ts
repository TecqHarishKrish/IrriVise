let sessionToken = localStorage.getItem('irrivise_session') || '';
let supportAccountId = localStorage.getItem('irrivise_support_account') || '';

export function getSessionToken() { return sessionToken; }
export function setSessionToken(t: string) {
  sessionToken = t;
  if (t) localStorage.setItem('irrivise_session', t);
  else localStorage.removeItem('irrivise_session');
}
export function setSupportAccountId(id: string) {
  supportAccountId = id;
  if (id) localStorage.setItem('irrivise_support_account', id);
  else localStorage.removeItem('irrivise_support_account');
}
export function getSupportAccountId() { return supportAccountId; }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      ...(supportAccountId ? { 'X-IrriVise-Support-Account': supportAccountId } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}
