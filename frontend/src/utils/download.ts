import * as WebBrowser from "expo-web-browser";
import { Platform } from "react-native";

import { api, apiBlob, grantUrl } from "@/src/api";

/**
 * Secure private downloads.
 * - Web: fetch with the Authorization header, hand the browser a local blob: URL (no token anywhere in a URL).
 * - Native: the in-app browser cannot send headers, so the server issues a single-use, 60-second grant
 *   scoped to this user + document; the user's access token is never placed in the URL.
 */
export async function openSecureDownload(opts: { headerPath: string; grantPath: string; filename: string }) {
  if (Platform.OS === "web") {
    const blob = await apiBlob(opts.headerPath);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = opts.filename;
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
    return;
  }
  const g = await api<{ url: string }>(opts.grantPath, { method: "POST" });
  await WebBrowser.openBrowserAsync(grantUrl(g.url));
}
