import { useQuery } from "@tanstack/react-query";
import { useFocusEffect, useRouter } from "expo-router";
import { BookOpenText, CheckCircle, Exam, ListChecks, NotePencil, UserCheck } from "phosphor-react-native";
import React from "react";
import { View } from "react-native";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Card, IconTile, Row, SectionTitle, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type Todo = { kind: "attendance" | "diary" | "homework_drafts" | "marks"; section_id?: string; title: string };
type WS = {
  date: string;
  schedule: { period: number; start: string; end: string; section_id: string; section_label: string; subject_name: string; room: string }[];
  todo: Todo[];
  counts: { periods_today: number; homework_due_today: number; homework_drafts: number; marks_sheets_pending: number; pending_leave: number; diary_written_today: number };
};

export function useWorkspace() {
  const { membership } = useAuth();
  return useQuery({ queryKey: ["teacher-workspace", membership?.school_id], queryFn: () => api<WS>("/teacher/workspace") });
}

/** Teacher Today: today's periods from the timetable + consolidated to-do list. */
export function TeacherWorkspace() {
  const { colors } = useTheme();
  const router = useRouter();
  const q = useWorkspace();
  const { refetch } = q;
  useFocusEffect(React.useCallback(() => { refetch(); }, [refetch])); // to-dos change after actions on other screens
  if (!q.data) return null;
  const d = q.data;
  const go = (t: Todo) => {
    if (t.kind === "attendance") router.push(`/attendance/${t.section_id}`);
    else if (t.kind === "diary") router.push(`/diary/${t.section_id}`);
    else if (t.kind === "homework_drafts") router.push("/homework");
    else router.push("/exams");
  };
  const icon = (k: Todo["kind"]) => (k === "attendance" ? <UserCheck size={18} color={colors.onBrandTertiary} /> : k === "diary" ? <BookOpenText size={18} color={colors.onBrandTertiary} /> : k === "marks" ? <Exam size={18} color={colors.onBrandTertiary} /> : <NotePencil size={18} color={colors.onBrandTertiary} />);
  return (
    <>
      <View>
        <SectionTitle title="Today's classes" action={<Badge testID="ws-periods-count" tone="brand" label={`${d.counts.periods_today} periods`} />} />
        <Card style={{ paddingVertical: d.schedule.length ? spacing.xs : spacing.lg }} testID="ws-schedule-card">
          {d.schedule.length ? d.schedule.map((s, i) => (
            <View key={`${s.period}-${s.section_id}`} testID={`ws-period-${s.period}`} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 52, borderBottomWidth: i === d.schedule.length - 1 ? 0 : 1, borderBottomColor: colors.divider }}>
              <View style={{ width: 56 }}>
                <Txt variant="label" raw>P{s.period}</Txt>
                <Txt variant="caption" raw>{s.start}</Txt>
              </View>
              <View style={{ flex: 1 }}>
                <Txt variant="label" raw numberOfLines={1}>{s.subject_name}</Txt>
                <Txt variant="caption" raw numberOfLines={1}>{s.section_label}{s.room ? ` · ${s.room}` : ""}</Txt>
              </View>
            </View>
          )) : <Txt variant="caption">No periods scheduled today.</Txt>}
        </Card>
      </View>
      <View>
        <SectionTitle title="To do" action={<Badge testID="ws-todo-count" tone={d.todo.length ? "warning" : "success"} label={d.todo.length ? `${d.todo.length} pending` : "All clear"} />} />
        <Card style={{ paddingVertical: 0 }} testID="ws-todo-card">
          {d.todo.length ? d.todo.map((t, i) => (
            <Row key={`${t.kind}-${t.section_id ?? i}`} testID={`ws-todo-${t.kind}-${t.section_id ?? "all"}`} last={i === d.todo.length - 1} icon={<IconTile>{icon(t.kind)}</IconTile>} title={t.title} onPress={() => go(t)} />
          )) : <Row testID="ws-todo-empty" last icon={<IconTile><CheckCircle size={18} color={colors.onBrandTertiary} /></IconTile>} title="You're all caught up" subtitle={`${d.counts.homework_due_today} homework due today`} />}
        </Card>
      </View>
      {d.counts.homework_due_today ? (
        <Row testID="ws-hw-due" icon={<IconTile><ListChecks size={18} color={colors.onBrandTertiary} /></IconTile>} title={`${d.counts.homework_due_today} homework due today`} subtitle="Track completion" onPress={() => router.push("/homework")} />
      ) : null}
    </>
  );
}
