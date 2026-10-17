import { useQuery } from "@tanstack/react-query";
import { addMonths, endOfMonth, startOfMonth } from "date-fns";
import { useRouter } from "expo-router";
import { CalendarBlank, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { CalItem, CalItemCard, covers, iso, MonthGrid } from "@/src/components/calendar";
import { EventDetail, EventForm } from "@/src/components/event-form";
import { Button, ChipRow, EmptyState, ErrorState, Header, SectionTitle, SkeletonList } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function SchoolCalendar() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const parent = membership?.role === "parent";
  const manager = can("notices.manage");
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [day, setDay] = useState<string | null>(null);
  const [child, setChild] = useState("all");
  const [open, setOpen] = useState<CalItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<CalItem | null>(null);
  const router = useRouter();
  const kids = useQuery({ queryKey: ["parent-children", membership?.school_id], enabled: parent, queryFn: () => api<{ items: { id: string; first_name: string }[] }>("/parent/children") });
  const range = `start=${iso(month)}&end=${iso(endOfMonth(month))}${parent && child !== "all" ? `&student_id=${child}` : ""}`;
  const q = useQuery({ queryKey: ["calendar", membership?.school_id, range], queryFn: () => api<{ items: CalItem[] }>(`/calendar?${range}`) });
  const items = q.data?.items ?? [];
  const shown = day ? items.filter((i) => covers(i, day)) : items;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="School calendar" subtitle="Events, holidays and exams" />
      {parent && (kids.data?.items.length ?? 0) > 1 ? (
        <ChipRow testIDPrefix="cal-child" value={child} onChange={setChild} options={[{ value: "all", label: "All children" }, ...kids.data!.items.map((k) => ({ value: k.id, label: k.first_name }))]} />
      ) : null}
      <FlatList
        testID="calendar-list"
        data={q.isLoading || q.isError ? [] : shown}
        keyExtractor={(i) => `${i.kind}-${i.id}-${i.start_date}`}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + (manager ? 120 : spacing.xl), gap: spacing.md, flexGrow: 1 }}
        ListHeaderComponent={
          <View style={{ gap: spacing.md }}>
            <MonthGrid month={month} items={items} selected={day} onSelect={setDay} onMonth={(d) => { setMonth(addMonths(month, d)); setDay(null); }} />
            <SectionTitle title={day ? formatDate(day) : "This month"} action={day ? <Button small variant="outline" testID="cal-show-month" title="Show month" onPress={() => setDay(null)} /> : undefined} />
          </View>
        }
        ListEmptyComponent={q.isLoading ? <SkeletonList rows={3} /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
          <EmptyState testID="calendar-empty" icon={<CalendarBlank size={40} color={colors.muted} />} title={day ? "Nothing on this day" : "Nothing scheduled"} message="School events, holidays and exam dates appear here." />
        )}
        renderItem={({ item }) => <CalItemCard i={item} onPress={() => setOpen(item)} />}
      />
      {manager ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="new-event-button" title="New event" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setCreating(true)} />
        </View>
      ) : null}
      {manager ? <EventForm visible={creating || !!editing} initial={editing} day={day ?? iso(new Date())} onClose={() => { setCreating(false); setEditing(null); }} /> : null}
      <EventDetail item={open} manager={manager} onClose={() => setOpen(null)} onEdit={(i) => { setOpen(null); setEditing(i); }} onOpenPtm={(i) => { setOpen(null); router.push(`/ptm/${i.id}`); }} />
    </View>
  );
}
