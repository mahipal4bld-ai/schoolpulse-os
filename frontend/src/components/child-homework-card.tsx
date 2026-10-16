import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { NotePencil } from "phosphor-react-native";
import React from "react";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Homework } from "@/src/components/homework";
import { Card, IconTile, Row, SectionTitle } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { useTheme } from "@/src/theme";

/** Parent home: upcoming homework for the selected child. */
export function ChildHomeworkCard({ studentId, name }: { studentId: string; name: string }) {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const q = useQuery({
    queryKey: ["parent-hw", membership?.school_id, studentId, "upcoming"],
    queryFn: () => api<{ items: Homework[] }>(`/parent/children/${studentId}/homework?scope=upcoming`),
  });
  const items = q.data?.items ?? [];
  const open = () => router.push({ pathname: "/child-homework/[studentId]", params: { studentId, name } });
  return (
    <>
      <SectionTitle title="Homework" />
      <Card style={{ paddingVertical: 0 }} testID="child-homework-card">
        {items.slice(0, 3).map((h) => (
          <Row key={h.id} testID={`child-hw-row-${h.id}`} icon={<IconTile><NotePencil size={18} color={colors.onBrandTertiary} /></IconTile>} title={`${h.subject_name}: ${h.title}`} subtitle={`Due ${formatDate(h.due_date)}`} onPress={open} />
        ))}
        <Row testID="child-homework-all" last title={items.length ? `View all (${items.length} upcoming)` : "No homework due"} subtitle="Upcoming and past homework" onPress={open} />
      </Card>
    </>
  );
}
