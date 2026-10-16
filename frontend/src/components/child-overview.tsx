import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import React from "react";
import { Pressable, View } from "react-native";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Card, SectionTitle, Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

type Overview = {
  date: string;
  attendance: { today: string | null; month_rate: number | null; days: number; absent: number };
  timetable_today: { period: number; start: string; subject_name: string }[];
  homework: { due_count: number; due_today: number; next: { id: string; title: string; subject_name: string; due_date: string }[] };
  diary_today: { kind: string; topic: string; subject_name: string | null }[];
  latest_result: { id: string; name: string; percentage: number | null; grade: string | null; result: string | null; rank: number | null; class_size: number } | null;
};

/** Parent home: glanceable "today at school" summary for the selected child. */
export function ChildOverview({ studentId, name }: { studentId: string; name: string }) {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const q = useQuery({ queryKey: ["parent-overview", membership?.school_id, studentId], queryFn: () => api<Overview>(`/parent/children/${studentId}/overview`) });
  if (!q.data) return null;
  const d = q.data;
  const p = { studentId, name };
  const tile = (testID: string, value: string, label: string, onPress: () => void) => (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => ({ flexBasis: "47%", flexGrow: 1, padding: spacing.md, borderRadius: radius.md, backgroundColor: pressed ? colors.surfaceTertiary : colors.surfaceSecondary, gap: 2 })}>
      <Txt variant="heading" raw>{value}</Txt>
      <Txt variant="caption" raw>{label}</Txt>
    </Pressable>
  );
  return (
    <View>
      <SectionTitle title="Today at school" />
      <Card testID="child-today-card" style={{ gap: spacing.md }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {tile("ov-attendance", d.attendance.today ? d.attendance.today : "—", `Today · ${d.attendance.month_rate ?? "—"}% this month`, () => {})}
          {tile("ov-homework", String(d.homework.due_count), `Homework due${d.homework.due_today ? ` · ${d.homework.due_today} today` : ""}`, () => router.push({ pathname: "/child-homework/[studentId]", params: p }))}
          {tile("ov-periods", String(d.timetable_today.length), "Periods today", () => router.push({ pathname: "/child-timetable/[studentId]", params: p }))}
          {tile("ov-result", d.latest_result?.percentage != null ? `${d.latest_result.percentage}%` : "—", d.latest_result ? `${d.latest_result.name}` : "No results yet", () => router.push({ pathname: "/child-exams/[studentId]", params: p }))}
        </View>
        {d.diary_today.length ? (
          <Pressable testID="ov-diary" onPress={() => router.push({ pathname: "/child-diary/[studentId]", params: p })} style={{ gap: 4 }}>
            <Txt variant="label">Learnt today</Txt>
            {d.diary_today.slice(0, 3).map((x, i) => (
              <Txt key={i} variant="caption" raw numberOfLines={1}>• {x.subject_name ? `${x.subject_name}: ` : ""}{x.topic}</Txt>
            ))}
          </Pressable>
        ) : null}
        {d.homework.next.length ? (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {d.homework.next.map((h) => <Badge key={h.id} tone="brand" label={`${h.subject_name}: ${h.title}`} />)}
          </View>
        ) : null}
      </Card>
    </View>
  );
}
