import { CaretLeft, CaretRight } from "phosphor-react-native";
import React from "react";
import { Pressable, View } from "react-native";

import { Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";
import { isoDay } from "@/src/components/homework";

export type DiaryEntry = { id: string; kind: "lesson" | "note"; subject_id: string | null; subject_name: string | null; topic: string; summary: string; date: string; author_name: string; created_by?: string };

export const shiftDay = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

/** Previous / next day stepper; never goes into the future. */
export function DayStepper({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { colors } = useTheme();
  const today = isoDay();
  const btn = { width: 44, height: 44, alignItems: "center" as const, justifyContent: "center" as const, borderRadius: radius.md };
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
      <Pressable testID="day-prev" onPress={() => onChange(shiftDay(value, -1))} style={btn} hitSlop={4}>
        <CaretLeft size={20} color={colors.brandPrimary} />
      </Pressable>
      <Txt variant="label" raw testID="day-label" style={{ flex: 1, textAlign: "center" }}>{value === today ? `Today · ${formatDate(value)}` : formatDate(value)}</Txt>
      <Pressable testID="day-next" disabled={value >= today} onPress={() => onChange(shiftDay(value, 1))} style={[btn, { opacity: value >= today ? 0.3 : 1 }]} hitSlop={4}>
        <CaretRight size={20} color={colors.brandPrimary} />
      </Pressable>
    </View>
  );
}

export function DiaryItem({ e, right }: { e: DiaryEntry; right?: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View testID={`diary-entry-${e.id}`} style={{ flexDirection: "row", gap: spacing.md, paddingVertical: spacing.md }}>
      <View style={{ width: 4, borderRadius: 2, backgroundColor: e.kind === "lesson" ? colors.brandPrimary : colors.brandSecondary }} />
      <View style={{ flex: 1, gap: 2 }}>
        <Txt variant="caption" raw>{e.kind === "lesson" ? e.subject_name : "Class note"} · {e.author_name}</Txt>
        <Txt variant="label" raw>{e.topic}</Txt>
        {e.summary ? <Txt variant="body" raw>{e.summary}</Txt> : null}
      </View>
      {right}
    </View>
  );
}
