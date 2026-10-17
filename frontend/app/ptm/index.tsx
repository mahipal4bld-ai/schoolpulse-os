import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { useRouter } from "expo-router";
import { CalendarCheck, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { DateField, TimeField } from "@/src/components/date-time-field";
import { Booking, BookingCard, datesLabel, InsightsPanel, PtmSession, SESSION_LABEL, SESSION_TONE, useInsights } from "@/src/components/ptm";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, Segmented, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

function SessionCard({ s, onPress }: { s: PtmSession; onPress: () => void }) {
  return (
    <Pressable testID={`ptm-session-${s.id}`} onPress={onPress} accessibilityRole="button">
      <Card style={{ gap: spacing.xs }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{s.name}</Txt>
          <Badge tone={SESSION_TONE[s.status]} label={SESSION_LABEL[s.status]} />
        </View>
        <Txt variant="caption" raw>{datesLabel(s)} · {s.start_time}–{s.end_time} IST</Txt>
        {s.capacity_total !== undefined ? <Txt variant="caption" raw>{`${s.booked_total}/${s.capacity_total} booked`}</Txt> : null}
      </Card>
    </Pressable>
  );
}

function AdminHome() {
  const { membership } = useAuth();
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [cls, setCls] = useState("all");
  const opts = useQuery({ queryKey: ["ptm-options"], queryFn: () => api<{ sections: { class_name: string }[] }>("/ptm/options") });
  const classes = [...new Set((opts.data?.sections ?? []).map((s) => s.class_name))];
  const qs = [from && `start=${from}`, to && `end=${to}`, cls !== "all" && `class_name=${encodeURIComponent(cls)}`].filter(Boolean).join("&");
  const ins = useInsights(membership?.school_id, qs);
  const q = useQuery({ queryKey: ["ptm-sessions", membership?.school_id], queryFn: () => api<{ items: PtmSession[] }>("/ptm/sessions?limit=50") });
  return (
    <View style={{ flex: 1 }}>
      <FlatList
        testID="ptm-admin-list"
        data={q.data?.items ?? []}
        keyExtractor={(s) => s.id}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); ins.refetch(); }} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.md }}
        ListHeaderComponent={
          <View style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 1 }}><DateField testID="ins-from" label="From" optional value={from} onChange={setFrom} /></View>
              <View style={{ flex: 1 }}><DateField testID="ins-to" label="To" optional value={to} min={from || undefined} onChange={setTo} /></View>
            </View>
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="ins-class" value={cls} onChange={setCls} options={[{ value: "all", label: "All classes" }, ...classes.map((c) => ({ value: c, label: c }))]} />
            </View>
            {ins.isLoading ? <SkeletonList rows={2} /> : ins.isError ? <ErrorState message={(ins.error as Error).message} onRetry={() => ins.refetch()} /> : <InsightsPanel d={ins.data!} />}
            <SectionTitle title="Sessions" />
            {q.isLoading ? <SkeletonList rows={3} /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : null}
          </View>
        }
        ListEmptyComponent={q.isLoading ? null : <EmptyState icon={<CalendarCheck size={40} color={colors.muted} />} title="No PTM sessions yet" message="Create a session, choose classes and teachers, and publish it for booking." />}
        renderItem={({ item }) => <SessionCard s={item} onPress={() => router.push(`/ptm/${item.id}`)} />}
      />
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Button testID="new-ptm-button" title="New PTM session" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => router.push("/ptm/new")} />
      </View>
    </View>
  );
}

function TeacherHome() {
  const { membership } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const today = format(new Date(), "yyyy-MM-dd");
  const [day, setDay] = useState(today);
  const [un, setUn] = useState<{ date: string; start: string; end: string; reason: string } | null>(null);
  const sch = useQuery({ queryKey: ["ptm-schedule", membership?.school_id, day], queryFn: () => api<{ items: Booking[] }>(`/ptm/schedule?day=${day}`) });
  const ses = useQuery({ queryKey: ["ptm-sessions", membership?.school_id], queryFn: () => api<{ items: PtmSession[] }>("/ptm/sessions") });
  const save = useMutation({
    mutationFn: () => api<{ blocked: number; requested: number; booked_conflicts: number }>("/ptm/unavailability", { body: { date: un!.date, start_time: un!.start, end_time: un!.end, reason: un!.reason } }),
    onSuccess: (r) => { setUn(null); qc.invalidateQueries({ queryKey: ["ptm-slots"] }); toast.show(`${r.blocked} blocked · ${r.requested} sent for approval${r.booked_conflicts ? ` · ${r.booked_conflicts} booked meeting(s) need the office` : ""}`); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <>
      <FlatList
        testID="ptm-teacher-schedule"
        data={sch.data?.items ?? []}
        keyExtractor={(b) => b.id}
        refreshControl={<RefreshControl refreshing={sch.isRefetching} onRefresh={() => { sch.refetch(); ses.refetch(); }} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}
        ListHeaderComponent={
          <View style={{ gap: spacing.md }}>
            <DateField testID="ptm-schedule-day" label="Meetings on" value={day} onChange={(d) => setDay(d || today)} />
            <SectionTitle title={`Schedule · ${formatDate(day)}`} />
            {sch.isLoading ? <SkeletonList rows={2} /> : sch.isError ? <ErrorState message={(sch.error as Error).message} onRetry={() => sch.refetch()} /> : null}
          </View>
        }
        ListEmptyComponent={sch.isLoading ? null : <EmptyState testID="ptm-schedule-empty" icon={<CalendarCheck size={36} color={colors.muted} />} title="No meetings on this day" message="Booked parent meetings appear here." />}
        renderItem={({ item }) => <BookingCard b={item} showGuardian onPress={() => router.push(`/ptm/booking/${item.id}`)} />}
        ListFooterComponent={
          <View style={{ gap: spacing.md, marginTop: spacing.lg }}>
            <SectionTitle title="My PTM sessions" action={<Button small variant="outline" testID="ptm-unavailable-button" title="I'm unavailable" onPress={() => setUn({ date: today, start: "", end: "", reason: "" })} />} />
            {(ses.data?.items ?? []).map((s) => <SessionCard key={s.id} s={s} onPress={() => router.push(`/ptm/${s.id}`)} />)}
            {ses.data && !ses.data.items.length ? <Txt variant="caption">You are not part of any PTM yet.</Txt> : null}
          </View>
        }
      />
      <Sheet visible={!!un} onClose={() => setUn(null)} title="Mark unavailable" testID="ptm-unavailable-sheet" footer={<Button testID="ptm-unavailable-save" title="Save" disabled={!un?.start || !un?.end || un.end <= un.start} loading={save.isPending} onPress={() => save.mutate()} />}>
        {un ? (
          <>
            <DateField testID="un-date" label="Date" value={un.date} min={today} onChange={(date) => setUn((p) => p && { ...p, date })} />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 1 }}><TimeField testID="un-start" label="From" value={un.start} onChange={(start) => setUn((p) => p && { ...p, start })} /></View>
              <View style={{ flex: 1 }}><TimeField testID="un-end" label="To" value={un.end} onChange={(end) => setUn((p) => p && { ...p, end })} error={un.start && un.end && un.end <= un.start ? "End time must be after the start time" : undefined} /></View>
            </View>
            <Field testID="un-reason" label="Reason (optional)" value={un.reason} onChangeText={(reason) => setUn((p) => p && { ...p, reason })} placeholder="e.g. Board duty" />
            <Txt variant="caption">Free slots in this period are blocked (or sent to the office for approval). Booked meetings are not changed.</Txt>
          </>
        ) : null}
      </Sheet>
    </>
  );
}

function ParentHome() {
  const { membership } = useAuth();
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const ses = useQuery({ queryKey: ["ptm-sessions", membership?.school_id], queryFn: () => api<{ items: PtmSession[] }>("/ptm/sessions") });
  const bk = useQuery({ queryKey: ["ptm-my", membership?.school_id, tab], queryFn: () => api<{ items: Booking[] }>(`/ptm/my-bookings?scope=${tab}`) });
  const open = (ses.data?.items ?? []).filter((s) => s.status === "published");
  return (
    <FlatList
      testID="ptm-parent-list"
      data={bk.data?.items ?? []}
      keyExtractor={(b) => b.id}
      refreshControl={<RefreshControl refreshing={bk.isRefetching} onRefresh={() => { bk.refetch(); ses.refetch(); }} tintColor={colors.brandPrimary} />}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}
      ListHeaderComponent={
        <View style={{ gap: spacing.md }}>
          <SectionTitle title="Book a meeting" />
          {ses.isLoading ? <SkeletonList rows={2} /> : ses.isError ? <ErrorState message={(ses.error as Error).message} onRetry={() => ses.refetch()} /> : open.length ? open.map((s) => <SessionCard key={s.id} s={s} onPress={() => router.push(`/ptm/${s.id}`)} />) : (
            <EmptyState testID="ptm-parent-no-sessions" icon={<CalendarCheck size={36} color={colors.muted} />} title="No meetings open for booking" message="When your school opens a parent–teacher meeting for your child's class, it appears here." />
          )}
          <Segmented testIDPrefix="ptm-tab" value={tab} onChange={setTab} options={[{ value: "upcoming", label: "My bookings" }, { value: "past", label: "History" }]} />
          {bk.isLoading ? <SkeletonList rows={2} /> : bk.isError ? <ErrorState message={(bk.error as Error).message} onRetry={() => bk.refetch()} /> : null}
        </View>
      }
      ListEmptyComponent={bk.isLoading ? null : <Txt variant="caption" testID="ptm-bookings-empty">{tab === "upcoming" ? "No upcoming meetings." : "No past meetings yet."}</Txt>}
      renderItem={({ item }) => <BookingCard b={item} onPress={() => router.push(`/ptm/booking/${item.id}`)} />}
    />
  );
}

export default function PtmHome() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const role = can("ptm.manage") ? "admin" : membership?.role === "teacher" ? "teacher" : membership?.role === "parent" ? "parent" : null;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Parent–teacher meetings" subtitle={role === "admin" ? "Sessions, bookings and insights" : role === "teacher" ? "Your meeting schedule" : "Book and manage meetings"} />
      {role === "admin" ? <AdminHome /> : role === "teacher" ? <TeacherHome /> : role === "parent" ? <ParentHome /> : <EmptyState title="Not available for your role" />}
    </View>
  );
}
