import { addDays, endOfMonth, endOfWeek, format, isSameMonth, startOfMonth, startOfWeek } from "date-fns";
import { CaretLeft, CaretRight } from "phosphor-react-native";
import React from "react";
import { Pressable, View } from "react-native";

import { Badge, Card, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export type CalItem = {
  id: string;
  kind: "event" | "exam" | "ptm";
  title: string;
  category: string;
  description: string;
  start_date: string;
  end_date: string;
  start_time: string | null;
  end_time: string | null;
  location: string;
  status: "draft" | "published" | "cancelled";
  cancel_reason?: string | null;
  papers?: { subject: string; date: string }[];
};

export const iso = (d: Date) => format(d, "yyyy-MM-dd");
export const covers = (i: CalItem, day: string) => i.start_date <= day && i.end_date >= day;

export function useDotColor() {
  const { colors } = useTheme();
  return (i: CalItem) => (i.status === "cancelled" ? colors.error : i.kind === "exam" ? colors.warning : i.kind === "ptm" ? colors.brandSecondary : i.category === "holiday" ? colors.success : colors.brandPrimary);
}

export function when(i: CalItem) {
  const d = i.start_date === i.end_date ? formatDate(i.start_date) : `${formatDate(i.start_date)} – ${formatDate(i.end_date)}`;
  return i.start_time ? `${d} · ${i.start_time}${i.end_time ? `–${i.end_time}` : ""}` : d;
}

/** Month grid (Mon-first) with coloured dots for days that have events or exams. */
export function MonthGrid({ month, items, selected, onSelect, onMonth, minDate }: { month: Date; items: CalItem[]; selected: string | null; onSelect: (d: string | null) => void; onMonth: (delta: number) => void; minDate?: string }) {
  const { colors } = useTheme();
  const dot = useDotColor();
  const today = iso(new Date());
  const days: Date[] = [];
  for (let d = startOfWeek(startOfMonth(month), { weekStartsOn: 1 }); d <= endOfWeek(endOfMonth(month), { weekStartsOn: 1 }); d = addDays(d, 1)) days.push(d);
  return (
    <Card style={{ gap: spacing.sm }} testID="month-grid">
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Pressable testID="cal-prev" onPress={() => onMonth(-1)} hitSlop={8} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><CaretLeft size={20} color={colors.onSurface} /></Pressable>
        <Txt variant="heading" raw style={{ flex: 1, textAlign: "center" }} testID="cal-month-label">{format(month, "MMMM yyyy")}</Txt>
        <Pressable testID="cal-next" onPress={() => onMonth(1)} hitSlop={8} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><CaretRight size={20} color={colors.onSurface} /></Pressable>
      </View>
      <View style={{ flexDirection: "row" }}>
        {["M", "T", "W", "T", "F", "S", "S"].map((w, i) => <Txt key={i} variant="caption" raw style={{ flex: 1, textAlign: "center" }}>{w}</Txt>)}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
        {days.map((d) => {
          const k = iso(d);
          const inMonth = isSameMonth(d, month) && !(minDate && k < minDate);
          const on = selected === k;
          const its = inMonth ? items.filter((i) => covers(i, k)) : [];
          return (
            <Pressable key={k} testID={`cal-day-${k}`} accessibilityRole="button" accessibilityLabel={`${format(d, "d MMMM")}${its.length ? `, ${its.length} items` : ""}`} disabled={!inMonth} onPress={() => onSelect(on ? null : k)} style={{ width: `${100 / 7}%`, height: 48, alignItems: "center", justifyContent: "center" }}>
              <View style={{ width: 36, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: on ? colors.brandPrimary : "transparent", borderWidth: k === today && !on ? 1 : 0, borderColor: colors.brandPrimary }}>
                <Txt variant="body" raw color={on ? colors.onBrandPrimary : inMonth ? colors.onSurface : colors.muted}>{format(d, "d")}</Txt>
              </View>
              <View style={{ flexDirection: "row", gap: 2, height: 6, marginTop: 1 }}>
                {its.slice(0, 3).map((i) => <View key={`${i.kind}-${i.id}`} style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: dot(i) }} />)}
              </View>
            </Pressable>
          );
        })}
      </View>
    </Card>
  );
}

export function CalItemCard({ i, onPress }: { i: CalItem; onPress: () => void }) {
  const { colors } = useTheme();
  const dot = useDotColor();
  const cancelled = i.status === "cancelled";
  return (
    <Pressable testID={`cal-item-${i.id}`} onPress={onPress}>
      <Card style={{ gap: spacing.xs, borderLeftWidth: 4, borderLeftColor: dot(i) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <Txt variant="caption" raw style={{ flex: 1 }}>{i.kind === "exam" ? "EXAM" : i.kind === "ptm" ? "PTM" : i.category.toUpperCase()} · {when(i)}</Txt>
          {cancelled ? <Badge tone="error" label="Cancelled" /> : i.status === "draft" ? <Badge tone="warning" label="Draft" /> : null}
        </View>
        <Txt variant="label" raw style={cancelled ? { textDecorationLine: "line-through", color: colors.onSurfaceTertiary } : undefined}>{i.title}</Txt>
        {i.location ? <Txt variant="caption" raw>{i.location}</Txt> : null}
      </Card>
    </Pressable>
  );
}
