import { useQuery } from "@tanstack/react-query";
import React, { useState } from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Card, ErrorState, Header, SectionTitle, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Intel = {
  window_days: number;
  from: string;
  to: string;
  working_days_with_attendance: number;
  attendance: { trend: { date: string; rate: number | null }[]; lowest_sections: { section_id: string; label: string; rate: number }[]; overall_rate: number | null; frequent_absentees: { student_id: string; name: string; absences: number }[] };
  coverage: { sections: { section_id: string; label: string; homework: number; diary_days: number }[]; sections_without_homework: number; sections_without_diary: number; homework_published: number };
  latest_exam: { id: string; name: string; sections: { section_id: string; label: string; average: number | null; pass_rate: number | null }[] } | null;
  staff: { present: number; late: number; absent: number; half_day: number; on_leave: number; marked: number; punctuality: number | null };
  leave_pending: number;
};

function Bar({ pct, color }: { pct: number; color: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" }}>
      <View style={{ height: 8, width: `${Math.max(0, Math.min(100, pct))}%`, backgroundColor: color }} />
    </View>
  );
}

function Line({ label, value, pct, testID }: { label: string; value: string; pct: number; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View testID={testID} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 28 }}>
      <Txt variant="caption" raw style={{ width: 92 }} numberOfLines={1}>{label}</Txt>
      <Bar pct={pct} color={colors.brandPrimary} />
      <Txt variant="label" raw style={{ width: 52, textAlign: "right" }}>{value}</Txt>
    </View>
  );
}

export default function AcademicInsights() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [days, setDays] = useState<"14" | "30">("14");
  const q = useQuery({ queryKey: ["academic-intel", membership?.school_id, days], queryFn: () => api<Intel>(`/dashboard/academic?days=${days}`) });
  const d = q.data;
  const maxHw = Math.max(1, ...(d?.coverage.sections.map((c) => c.homework) ?? [1]));
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Academic insights" subtitle={d ? `${formatDate(d.from)} – ${formatDate(d.to)}` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : d ? (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
          <Segmented testIDPrefix="intel-window" value={days} onChange={setDays} options={[{ value: "14", label: "14 days" }, { value: "30", label: "30 days" }]} />
          <View>
            <SectionTitle title="Student attendance" action={<Badge testID="intel-att-overall" tone="brand" label={d.attendance.overall_rate === null ? "No data" : `${d.attendance.overall_rate}% overall`} />} />
            <Card style={{ gap: spacing.md }} testID="intel-attendance-card">
              <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 3, height: 64 }}>
                {d.attendance.trend.map((t) => <View key={t.date} style={{ flex: 1, height: t.rate === null ? 3 : Math.max(3, (t.rate / 100) * 64), borderRadius: 2, backgroundColor: t.rate === null ? colors.surfaceTertiary : colors.brandSecondary }} />)}
              </View>
              <Txt variant="caption" raw>{d.working_days_with_attendance} day(s) with attendance recorded</Txt>
              {d.attendance.lowest_sections.length ? <Txt variant="label">Lowest attendance</Txt> : null}
              {d.attendance.lowest_sections.map((s) => <Line key={s.section_id} testID={`intel-low-${s.section_id}`} label={s.label} value={`${s.rate}%`} pct={s.rate} />)}
              {d.attendance.frequent_absentees.length ? (
                <View style={{ gap: 4 }}>
                  <Txt variant="label">Frequently absent (3+ days)</Txt>
                  {d.attendance.frequent_absentees.map((a) => <Txt key={a.student_id} variant="caption" raw>{a.name} · {a.absences} days</Txt>)}
                </View>
              ) : null}
            </Card>
          </View>
          <View>
            <SectionTitle title="Homework & diary coverage" />
            <Card style={{ gap: spacing.sm }} testID="intel-coverage-card">
              <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                <Badge tone="brand" label={`${d.coverage.homework_published} homework published`} />
                {d.coverage.sections_without_homework ? <Badge testID="intel-no-hw" tone="warning" label={`${d.coverage.sections_without_homework} sections without homework`} /> : null}
                {d.coverage.sections_without_diary ? <Badge tone="warning" label={`${d.coverage.sections_without_diary} sections without diary`} /> : null}
              </View>
              {d.coverage.sections.map((c) => <Line key={c.section_id} testID={`intel-cov-${c.section_id}`} label={c.label} value={`${c.homework} · ${c.diary_days}d`} pct={(100 * c.homework) / maxHw} />)}
              <Txt variant="caption">Homework published · days with a diary entry</Txt>
            </Card>
          </View>
          <View>
            <SectionTitle title="Latest exam results" />
            <Card style={{ gap: spacing.sm }} testID="intel-exam-card">
              {d.latest_exam ? (
                <>
                  <Txt variant="label" raw>{d.latest_exam.name}</Txt>
                  {d.latest_exam.sections.map((s) => <Line key={s.section_id} label={s.label} value={s.average === null ? "—" : `${s.average}%`} pct={s.average ?? 0} />)}
                </>
              ) : <Txt variant="caption">No published exam yet.</Txt>}
            </Card>
          </View>
          <View>
            <SectionTitle title="Staff" />
            <Card style={{ gap: spacing.xs }} testID="intel-staff-card">
              <Txt variant="body" raw>Punctuality {d.staff.punctuality ?? "—"}% · Late {d.staff.late} · Absent {d.staff.absent} · Leave {d.staff.on_leave}</Txt>
              <Txt variant="caption" raw>{d.leave_pending} leave request(s) pending</Txt>
            </Card>
          </View>
        </ScrollView>
      ) : null}
    </View>
  );
}
