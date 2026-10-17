import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { CalendarBlank, ChatsCircle, Megaphone } from "phosphor-react-native";
import React from "react";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Card, IconTile, Row } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { useTheme } from "@/src/theme";

/** Parent home entry to school notices with unread count. */
export function ParentNoticesRow() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const q = useQuery({ queryKey: ["parent-notices", membership?.school_id], queryFn: () => api<{ items: { id: string; title: string; requires_ack: boolean; acknowledged: boolean }[]; unread: number }>("/parent/notices") });
  const up = useQuery({ queryKey: ["calendar", membership?.school_id, "upcoming"], queryFn: () => api<{ items: { title: string; start_date: string }[] }>("/calendar/upcoming?limit=1") });
  const next = up.data?.items[0];
  const pendingAck = q.data?.items.filter((n) => n.requires_ack && !n.acknowledged).length ?? 0;
  return (
    <Card style={{ paddingVertical: 0 }} testID="parent-notices-card">
      <Row testID="open-parent-messages" icon={<IconTile><ChatsCircle size={18} color={colors.onBrandTertiary} /></IconTile>} title="Messages" subtitle="Talk to your child's teachers" onPress={() => router.push("/messages")} />
      <Row testID="open-parent-calendar" icon={<IconTile><CalendarBlank size={18} color={colors.onBrandTertiary} /></IconTile>} title="School calendar" subtitle={next ? `Next: ${next.title} · ${formatDate(next.start_date)}` : "Events, holidays and exams"} onPress={() => router.push("/calendar")} />
      <Row testID="open-parent-notices" last icon={<IconTile><Megaphone size={18} color={colors.onBrandTertiary} /></IconTile>} title="School notices" subtitle={q.data ? (q.data.unread ? `${q.data.unread} new${pendingAck ? ` · ${pendingAck} need acknowledgement` : ""}` : pendingAck ? `${pendingAck} need acknowledgement` : "You're up to date") : "Announcements from school"} onPress={() => router.push("/parent-notices")} />
    </Card>
  );
}
