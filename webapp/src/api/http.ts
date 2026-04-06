import { BASE_URL } from "@/api.tsx";

export const API_BASE = BASE_URL;

export async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
