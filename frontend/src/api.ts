import { Platform } from "react-native";

export const API_BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

let token: string | null = null;
let refreshToken: string | null = null;
let schoolId: string | null = null;
let onUnauthorized: (() => void) | null = null;
let onTokens: ((access: string, refresh: string) => void) | null = null;
let onSchoolInactive: (() => void) | null = null;
let refreshing: Promise<boolean> | null = null;

export const session = {
  setToken: (t: string | null) => (token = t),
  setRefreshToken: (t: string | null) => (refreshToken = t),
  setSchool: (s: string | null) => (schoolId = s),
  getSchool: () => schoolId,
  onUnauthorized: (fn: () => void) => (onUnauthorized = fn),
  onTokens: (fn: (access: string, refresh: string) => void) => (onTokens = fn),
  onSchoolInactive: (fn: () => void) => (onSchoolInactive = fn),
};

// Single-flight refresh: concurrent 401s share one rotation (prevents false reuse detection).
export function refreshSession(): Promise<boolean> {
  if (!refreshToken) return Promise.resolve(false);
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!r.ok) return false;
      const d = await r.json();
      token = d.access_token;
      refreshToken = d.refresh_token;
      onTokens?.(d.access_token, d.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
        const msg = String(d.msg || "").replace(/^Value error, /, "");
        return field && field !== "body" ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
      })
      .join("\n");
  }
  return "Something went wrong";
}

type Opts = { method?: string; body?: unknown; form?: FormData; noSchool?: boolean; _retried?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (schoolId && !opts.noSchool) headers["X-School-Id"] = schoolId;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: opts.method || (opts.body !== undefined || opts.form ? "POST" : "GET"),
      headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    });
  } catch {
    throw new ApiError(0, "You appear to be offline. Check your connection and try again.");
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const message = detailToMessage(data?.detail);
    if (res.status === 401 && token && !path.startsWith("/auth/login") && !opts._retried) {
      if (await refreshSession()) return api<T>(path, { ...opts, _retried: true });
      onUnauthorized?.();
    } else if (res.status === 401 && token && opts._retried) {
      onUnauthorized?.();
    }
    if (res.status === 403 && /school account is not active/i.test(message)) onSchoolInactive?.();
    throw new ApiError(res.status, message);
  }
  return data as T;
}

export function fileUrl(id?: string | null) {
  return id ? `${API_BASE}/files/${id}` : null;
}

export async function uploadImage(uri: string, purpose: "logo" | "banner" | "photo", mime = "image/jpeg") {
  const name = `${purpose}.${mime.split("/")[1] || "jpg"}`;
  const form = new FormData();
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    form.append("file", blob, name);
  } else {
    form.append("file", { uri, name, type: mime } as any);
  }
  return api<{ id: string }>(`/uploads?purpose=${purpose}`, { form, method: "POST" });
}

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number; has_more: boolean };
