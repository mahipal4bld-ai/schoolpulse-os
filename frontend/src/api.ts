import { Platform } from "react-native";

export const API_BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

let token: string | null = null;
let schoolId: string | null = null;
let onUnauthorized: (() => void) | null = null;

export const session = {
  setToken: (t: string | null) => (token = t),
  setSchool: (s: string | null) => (schoolId = s),
  getSchool: () => schoolId,
  onUnauthorized: (fn: () => void) => (onUnauthorized = fn),
};

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

type Opts = { method?: string; body?: unknown; form?: FormData; noSchool?: boolean };

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
    if (res.status === 401 && token) onUnauthorized?.();
    throw new ApiError(res.status, detailToMessage(data?.detail));
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
