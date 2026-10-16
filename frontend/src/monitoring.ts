// Production-safe client error reporting. Messages are scrubbed of tokens, emails, phone numbers
// and long digit runs before leaving the device; no request bodies, headers or user data are sent.
import { Platform } from "react-native";

import { API_BASE, session } from "@/src/api";

const PATTERNS: [RegExp, string][] = [
  [/eyJ[\w-]+\.[\w-]+\.[\w-]+/g, "[jwt]"],
  [/(bearer|token|password|refresh_token|access_token)["'=:\s]+[^\s"',}]+/gi, "$1=[redacted]"],
  [/[\w.+-]+@[\w-]+\.[\w.]+/g, "[email]"],
  [/\b[6-9]\d{9}\b/g, "[phone]"],
  [/\d{6,}/g, "[num]"],
];

export function scrub(text: string): string {
  return PATTERNS.reduce((t, [rx, rep]) => t.replace(rx, rep), String(text)).slice(0, 2000);
}

let sent = 0;
export function reportError(error: unknown, kind: "render" | "global" | "promise", stack = "") {
  if (sent >= 20) return; // per app session cap
  sent += 1;
  const e = error instanceof Error ? error : new Error(String(error));
  const body = { kind, message: scrub(e.message), stack: scrub(`${e.stack ?? ""}\n${stack}`), platform: Platform.OS, school: session.getSchool() };
  fetch(`${API_BASE}/client-errors`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => {});
}

export function installGlobalHandlers() {
  const g: any = global as any;
  const prev = g.ErrorUtils?.getGlobalHandler?.();
  g.ErrorUtils?.setGlobalHandler?.((err: Error, fatal?: boolean) => {
    reportError(err, "global");
    prev?.(err, fatal);
  });
}
