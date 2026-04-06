const DEFAULT_BASE = "http://localhost:8080";
export const API_BASE = import.meta.env.VITE_API_BASE || DEFAULT_BASE;

export async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
