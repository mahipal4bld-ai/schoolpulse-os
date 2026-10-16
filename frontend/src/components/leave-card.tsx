import React from "react";
import { View } from "react-native";

import { Badge, Card, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing } from "@/src/theme";

export type Leave = {
  id: string;
  teacher_name: string;
  designation: string;
  type: string;
  from_date: string;
  to_date: string;
  days: number;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  decision_note: string | null;
};
const LEAVE_TONE = { pending: "warning", approved: "success", rejected: "error", cancelled: "neutral" } as const;

export function LeaveCard({ lv, footer }: { lv: Leave; footer?: React.ReactNode }) {
  return (
    <Card testID={`leave-card-${lv.id}`} style={{ gap: spacing.sm }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <Txt variant="label" raw numberOfLines={1}>{lv.teacher_name}</Txt>
          <Txt variant="caption" raw>{lv.designation}</Txt>
        </View>
        <Badge testID={`leave-status-${lv.id}`} tone={LEAVE_TONE[lv.status]} label={lv.status} />
      </View>
      <Txt variant="body" raw>
        {lv.type} · {formatDate(lv.from_date)}{lv.to_date !== lv.from_date ? ` – ${formatDate(lv.to_date)}` : ""} · {lv.days} day{lv.days > 1 ? "s" : ""}
      </Txt>
      <Txt variant="caption" raw>{lv.reason}</Txt>
      {lv.decision_note ? <Txt variant="caption" raw>Note: {lv.decision_note}</Txt> : null}
      {footer}
    </Card>
  );
}
