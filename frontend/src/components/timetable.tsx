import { useQuery } from "@tanstack/react-query";
import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Card, ErrorState, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export type Slot = { day: number; period: number; section_id: string; section_label: string; subject_id: string; subject_name: string; teacher_id?: string | null; teacher_name?: string | null; room: string };
export type Grid = { periods: { no: number; start: string; end: string }[]; days: { day: number; name: string }[]; slots: Slot[]; today: number; section?: string; teacher?: string | null };

export function DayTabs({ grid, day, onChange }: { grid: Grid; day: number; onChange: (d: number) => void }) {
  return <Segmented testIDPrefix="tt-day" value={String(day)} onChange={(v) => onChange(Number(v))} options={grid.days.map((d) => ({ value: String(d.day), label: d.name }))} />;
}

/** One day's periods. `show` picks what the second line shows (teacher for class view, section for teacher view). */
export function DaySchedule({ grid, day, show, onPress, testIDPrefix = "tt-period" }: { grid: Grid; day: number; show: "teacher" | "section" | "none"; onPress?: (period: number, slot?: Slot) => void; testIDPrefix?: string }) {
  const { colors } = useTheme();
  const byPeriod = new Map(grid.slots.filter((s) => s.day === day).map((s) => [s.period, s]));
  return (
    <Card style={{ paddingVertical: spacing.xs }}>
      {grid.periods.map((p, i) => {
        const s = byPeriod.get(p.no);
        const sub = s ? (show === "teacher" ? s.teacher_name ?? "No teacher" : show === "section" ? s.section_label : "") : "";
        return (
          <Pressable
            key={p.no}
            testID={`${testIDPrefix}-${p.no}`}
            disabled={!onPress}
            onPress={() => onPress?.(p.no, s)}
            style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 56, paddingVertical: spacing.sm, borderBottomWidth: i === grid.periods.length - 1 ? 0 : 1, borderBottomColor: colors.divider, opacity: pressed ? 0.7 : 1 })}
          >
            <View style={{ width: 56 }}>
              <Txt variant="label" raw>P{p.no}</Txt>
              <Txt variant="caption" raw>{p.start}</Txt>
            </View>
            {s ? (
              <View style={{ flex: 1, gap: 2 }}>
                <Txt variant="label" raw numberOfLines={1}>{s.subject_name}</Txt>
                {sub || s.room ? <Txt variant="caption" raw numberOfLines={1}>{[sub, s.room].filter(Boolean).join(" · ")}</Txt> : null}
              </View>
            ) : (
              <View style={{ flex: 1, paddingVertical: 6, paddingHorizontal: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary }}>
                <Txt variant="caption" raw>{onPress ? "Free · tap to assign" : "Free"}</Txt>
              </View>
            )}
          </Pressable>
        );
      })}
    </Card>
  );
}

/** Shared read-only weekly timetable for teacher ("/my-timetable") and parent ("/child-timetable/[id]") views. */
export function WeeklyTimetable({ path, queryKey, title, subtitle, show }: { path: string; queryKey: unknown[]; title: string; subtitle?: string; show: "teacher" | "section" | "none" }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey, queryFn: () => api<Grid>(path) });
  const [picked, setDay] = useState<number | null>(null);
  const t = q.data?.today ?? 1;
  const day = picked ?? (t >= 1 && t <= 6 ? t : 1);
  const count = q.data?.slots.filter((s) => s.day === day).length ?? 0;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={title} subtitle={subtitle} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}>
          <DayTabs grid={q.data!} day={day} onChange={setDay} />
          <Txt variant="caption" raw testID="tt-day-count">{count} period(s)</Txt>
          <DaySchedule grid={q.data!} day={day} show={show} />
        </ScrollView>
      )}
    </View>
  );
}

