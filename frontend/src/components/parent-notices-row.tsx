import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Megaphone } from "phosphor-react-native";
import React from "react";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Card, IconTile, Row } from "@/src/components/ui";
import { useTheme } from "@/src/theme";

/** Parent home entry to school notices with unread count. */
export function ParentNoticesRow() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const q = useQuery({ queryKey: ["parent-notices", membership?.school_id], queryFn: () => api<{ items: { id: string; title: string; requires_ack: boolean; acknowledged: boolean }[]; unread: number }>("/parent/notices") });
  const pendingAck = q.data?.items.filter((n) => n.requires_ack && !n.acknowledged).length ?? 0;
  return (
    <Card style={{ paddingVertical: 0 }} testID="parent-notices-card">
      <Row testID="open-parent-notices" last icon={<IconTile><Megaphone size={18} color={colors.onBrandTertiary} /></IconTile>} title="School notices" subtitle={q.data ? (q.data.unread ? `${q.data.unread} new${pendingAck ? ` · ${pendingAck} need acknowledgement` : ""}` : pendingAck ? `${pendingAck} need acknowledgement` : "You're up to date") : "Announcements from school"} onPress={() => router.push("/parent-notices")} />
    </Card>
  );
}
