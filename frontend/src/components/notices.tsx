import React from "react";
import { View } from "react-native";

import { Badge, Card, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { AttachmentList, Attachment } from "@/src/components/homework";
import { spacing, useTheme } from "@/src/theme";

export type Notice = {
  id: string;
  title: string;
  body: string;
  category: string;
  priority: "normal" | "important" | "urgent";
  status: string;
  requires_ack: boolean;
  publish_at: string | null;
  published_at: string | null;
  attachments: Attachment[];
  read?: boolean;
  acknowledged?: boolean;
  revision_count?: number;
  stats?: { audience: number; read: number; acknowledged: number };
};
export const PRIORITY_TONE = { normal: "neutral", important: "warning", urgent: "error" } as const;

/** School-branded notice card (brand colour accent bar). */
export function NoticeCard({ n, footer }: { n: Notice; footer?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <Card testID={`notice-${n.id}`} style={{ gap: spacing.sm, borderLeftWidth: 4, borderLeftColor: n.priority === "urgent" ? colors.error : n.priority === "important" ? colors.warning : colors.brandPrimary }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Txt variant="caption" raw style={{ flex: 1 }}>{n.category.toUpperCase()}{n.published_at ? ` · ${formatDateTime(n.published_at)}` : ""}</Txt>
        {n.priority !== "normal" ? <Badge tone={PRIORITY_TONE[n.priority]} label={n.priority} /> : null}
        {n.read === false ? <Badge testID={`notice-unread-${n.id}`} tone="brand" label="New" /> : null}
      </View>
      <Txt variant="label" raw>{n.title}</Txt>
      <Txt variant="body" raw>{n.body}</Txt>
      <AttachmentList items={n.attachments} testIDPrefix="notice-file" />
      {footer}
    </Card>
  );
}
