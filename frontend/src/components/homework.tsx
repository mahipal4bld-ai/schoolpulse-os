import * as WebBrowser from "expo-web-browser";
import { FilePdf, ImageSquare } from "phosphor-react-native";
import React from "react";
import { Pressable, View } from "react-native";

import { privateFileUrl } from "@/src/api";
import { Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export type Attachment = { id: string; name: string; content_type: string; size: number };
export type Homework = {
  id: string;
  section_id: string;
  subject_id: string;
  section_label: string;
  subject_name: string;
  title: string;
  description: string;
  assigned_date: string;
  due_date: string;
  status: "draft" | "published";
  attachments: Attachment[];
  completion_counts?: { done: number; not_done: number; late: number };
  students?: { id: string; name: string; roll_no?: number; status: Completion | null }[];
  my_status?: Completion | null;
};
export type Completion = "done" | "not_done" | "late";

export const isoDay = (offset = 0) => new Date(Date.now() + 5.5 * 3600e3 + offset * 86400e3).toISOString().slice(0, 10);

export function AttachmentList({ items, testIDPrefix = "attachment" }: { items: Attachment[]; testIDPrefix?: string }) {
  const { colors } = useTheme();
  if (!items.length) return null;
  return (
    <View style={{ gap: spacing.sm }}>
      {items.map((a) => (
        <Pressable
          key={a.id}
          testID={`${testIDPrefix}-${a.id}`}
          onPress={() => WebBrowser.openBrowserAsync(privateFileUrl(a.id)).catch(() => {})}
          style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: pressed ? colors.surfaceSecondary : colors.surface })}
        >
          {a.content_type === "application/pdf" ? <FilePdf size={20} color={colors.brandPrimary} /> : <ImageSquare size={20} color={colors.brandPrimary} />}
          <Txt variant="body" raw numberOfLines={1} style={{ flex: 1 }}>{a.name}</Txt>
          <Txt variant="caption" raw>{Math.max(1, Math.round(a.size / 1024))} KB</Txt>
        </Pressable>
      ))}
    </View>
  );
}
