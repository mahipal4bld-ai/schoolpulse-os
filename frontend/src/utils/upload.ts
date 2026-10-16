import { Platform } from "react-native";

import { api } from "@/src/api";

/** Cross-platform multipart upload (web + native). Never set Content-Type manually. */
export async function uploadForm<T = any>(path: string, file: { uri: string; name: string; type: string }, field = "file"): Promise<T> {
  const form = new FormData();
  let blob: Blob;
  if (Platform.OS === "web") {
    blob = await (await fetch(file.uri)).blob();
  } else {
    const { fetch: expoFetch } = await import("expo/fetch");
    blob = await (await expoFetch(file.uri)).blob();
  }
  form.append(field, new Blob([blob], { type: file.type }) as any, file.name);
  return api<T>(path, { form, method: "POST" });
}
