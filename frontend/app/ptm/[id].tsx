import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CheckCircle } from "phosphor-react-native";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { timeLabel } from "@/src/components/date-time-field";
import { Booking, BookingCard, datesLabel, PtmSession, SESSION_TONE, Slot, SlotGrid, slotWhen } from "@/src/components/ptm";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type ParentSession = PtmSession & { children: { student_id: string; name: string; teachers: { teacher_id: string; name: string }[] }[] };
type AdminSession = PtmSession & { teachers: { teacher_id: string; name: string; slots: number; cap: number; booked: number; blocked: number; requests: number }[]; section_labels: string[]; stats: { booked: number; capacity: number; by_status: Record<string, number> } };
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

function Policy({ s }: { s: PtmSession }) {
  return (
    <Txt variant="caption" raw testID="ptm-policy">
      {`${s.mode === "online" ? "Online meeting" : `In person${s.location ? ` · ${s.location}` : ""}`} · ${s.slot_minutes} min. Cancel up to ${s.cancel_cutoff_hours}h and reschedule up to ${s.reschedule_cutoff_hours}h before the meeting. Up to ${s.max_per_child} meeting(s) per child.`}
    </Txt>
  );
}

function ParentBook({ s }: { s: ParentSession }) {
  const { membership } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [child, setChild] = useState(s.children[0]?.student_id ?? "");
  const kid = s.children.find((c) => c.student_id === child);
  const [teacher, setTeacher] = useState("");
  const tid = teacher && kid?.teachers.some((t) => t.teacher_id === teacher) ? teacher : kid?.teachers[0]?.teacher_id ?? "";
  const [pick, setPick] = useState<Slot | null>(null);
  const [cid, setCid] = useState(newId);
  const slots = useQuery({ queryKey: ["ptm-slots", membership?.school_id, s.id, tid, child], enabled: !!tid, refetchInterval: 15000, queryFn: () => api<{ items: Slot[] }>(`/ptm/sessions/${s.id}/slots?teacher_id=${tid}&student_id=${child}`) });
  const book = useMutation({
    mutationFn: () => api<Booking>("/ptm/bookings", { body: { slot_id: pick!.id, student_id: child, client_id: cid } }),
    onSuccess: (b) => { setPick(null); setCid(newId()); qc.invalidateQueries({ queryKey: ["ptm-my"] }); qc.invalidateQueries({ queryKey: ["ptm-slots"] }); toast.show("Booking confirmed"); router.push(`/ptm/booking/${b.id}`); },
    onError: (e: Error) => { setCid(newId()); slots.refetch(); toast.show(e.message, "error"); },  // retry of a network failure reuses cid until it resolves
  });
  const tName = kid?.teachers.find((t) => t.teacher_id === tid)?.name;
  return (
    <View style={{ gap: spacing.lg }}>
      {s.children.length > 1 ? (
        <View style={{ gap: spacing.sm }}>
          <Txt variant="overline">1 · Choose child</Txt>
          <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ptm-child" value={child} onChange={(c) => { setChild(c); setTeacher(""); setPick(null); }} options={s.children.map((c) => ({ value: c.student_id, label: c.name }))} /></View>
        </View>
      ) : null}
      <View style={{ gap: spacing.sm }}>
        <Txt variant="overline">{s.children.length > 1 ? "2 · Choose teacher" : "1 · Choose teacher"}</Txt>
        {kid?.teachers.length ? <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ptm-teacher" value={tid} onChange={(t) => { setTeacher(t); setPick(null); }} options={kid.teachers.map((t) => ({ value: t.teacher_id, label: t.name }))} /></View> : <Txt variant="caption">No teachers are taking bookings for this child.</Txt>}
      </View>
      {tid ? (
        <View style={{ gap: spacing.sm }}>
          <Txt variant="overline">{s.children.length > 1 ? "3 · Choose a time" : "2 · Choose a time"}</Txt>
          {slots.isLoading ? <SkeletonList rows={2} /> : slots.isError ? <ErrorState message={(slots.error as Error).message} onRetry={() => slots.refetch()} /> :
            slots.data!.items.some((x) => x.available) ? <SlotGrid slots={slots.data!.items} selected={pick?.id} onPick={setPick} /> : <EmptyState testID="ptm-no-slots" title="Fully booked" message="All times with this teacher are taken. Try another teacher or check back later." />}
        </View>
      ) : null}
      <Sheet visible={!!pick} onClose={() => setPick(null)} title="Confirm booking" testID="ptm-confirm-sheet" footer={<Button testID="ptm-confirm-book" title="Confirm booking" loading={book.isPending} onPress={() => book.mutate()} />}>
        {pick ? (
          <View style={{ gap: spacing.sm }}>
            <Txt variant="heading" raw>{slotWhen(pick.date, pick.start_time, pick.end_time)} IST</Txt>
            <Txt variant="body" raw>{`${tName} · ${kid?.name}`}</Txt>
            <Policy s={s} />
          </View>
        ) : null}
      </Sheet>
    </View>
  );
}

function StaffSlots({ s, teacherId, admin }: { s: PtmSession; teacherId: string; admin: boolean }) {
  const { membership } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [sel, setSel] = useState<Slot | null>(null);
  const [reason, setReason] = useState("");
  const slots = useQuery({ queryKey: ["ptm-slots", membership?.school_id, s.id, teacherId], queryFn: () => api<{ items: Slot[] }>(`/ptm/sessions/${s.id}/slots?teacher_id=${teacherId}`) });
  const act = useMutation({
    mutationFn: (a: string) => api(`/ptm/slots/${sel!.id}/availability?act=${a}&reason=${encodeURIComponent(reason)}`, { method: "POST" }),
    onSuccess: () => { setSel(null); setReason(""); slots.refetch(); qc.invalidateQueries({ queryKey: ["ptm-session"] }); toast.show("Availability updated"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  if (slots.isLoading) return <SkeletonList rows={2} />;
  if (slots.isError) return <ErrorState message={(slots.error as Error).message} onRetry={() => slots.refetch()} />;
  const live = s.status === "published";
  return (
    <>
      <SlotGrid staff slots={slots.data!.items} selected={sel?.id} onPick={setSel} />
      <Sheet visible={!!sel} onClose={() => setSel(null)} title={sel ? `${timeLabel(sel.start_time)} – ${timeLabel(sel.end_time)}` : ""} testID="ptm-slot-sheet">
        {sel ? (
          <View style={{ gap: spacing.md }}>
            {sel.bookings?.map((b) => <Button key={b.booking_id} variant="outline" testID={`ptm-slot-booking-${b.booking_id}`} title={`${b.student_name} (${b.class_label}) · ${b.guardian_name}`} onPress={() => { setSel(null); router.push(`/ptm/booking/${b.booking_id}`); }} />)}
            {sel.block_reason ? <Txt variant="caption" raw>{sel.block_reason}</Txt> : null}
            {live ? (
              <>
                {admin || sel.status === "available" ? <Field testID="ptm-slot-reason" label={admin ? "Reason (required for overrides)" : "Reason (optional)"} value={reason} onChangeText={setReason} placeholder="e.g. Staff meeting" /> : null}
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                  {sel.status === "available" && !sel.booked ? <Button small testID="ptm-slot-block" title="Mark unavailable" onPress={() => act.mutate("block")} loading={act.isPending} /> : null}
                  {sel.status === "blocked" || sel.status === "block_requested" ? <Button small variant="outline" testID="ptm-slot-unblock" title="Re-open slot" onPress={() => act.mutate("unblock")} loading={act.isPending} /> : null}
                  {admin && sel.status === "block_requested" ? <Button small testID="ptm-slot-approve" title="Approve request" onPress={() => act.mutate("approve")} /> : null}
                  {admin && sel.status === "block_requested" ? <Button small variant="outline" testID="ptm-slot-reject" title="Reject request" onPress={() => act.mutate("reject")} /> : null}
                </View>
              </>
            ) : null}
          </View>
        ) : null}
      </Sheet>
    </>
  );
}

function AdminView({ s }: { s: AdminSession }) {
  const { membership } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [teacher, setTeacher] = useState(s.teachers[0]?.teacher_id ?? "");
  const [cancel, setCancel] = useState<string | null>(null);
  const bk = useQuery({ queryKey: ["ptm-session-bookings", membership?.school_id, s.id], enabled: s.status !== "draft", queryFn: () => api<{ items: Booking[]; total: number }>(`/ptm/sessions/${s.id}/bookings?limit=100`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["ptm-session"] }); qc.invalidateQueries({ queryKey: ["ptm-sessions"] }); qc.invalidateQueries({ queryKey: ["calendar"] }); qc.invalidateQueries({ queryKey: ["ptm-insights"] }); };
  const publish = useMutation({ mutationFn: () => api(`/ptm/sessions/${s.id}/publish`, { method: "POST" }), onSuccess: () => { refresh(); toast.show("PTM published"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const doCancel = useMutation({ mutationFn: () => api<{ bookings_cancelled: number }>(`/ptm/sessions/${s.id}/cancel?reason=${encodeURIComponent(cancel ?? "")}`, { method: "POST" }), onSuccess: (r) => { setCancel(null); refresh(); bk.refetch(); toast.show(`Session cancelled · ${r.bookings_cancelled} booking(s) cancelled`); }, onError: (e: Error) => toast.show(e.message, "error") });
  const util = s.stats.capacity ? Math.round((s.stats.booked / s.stats.capacity) * 100) : 0;
  return (
    <View style={{ gap: spacing.lg }}>
      <Card style={{ gap: spacing.xs }} testID="ptm-session-stats">
        <Txt variant="heading" raw>{`${s.stats.booked}/${s.stats.capacity} booked · ${util}%`}</Txt>
        <Txt variant="caption" raw>{`Completed ${s.stats.by_status.completed ?? 0} · No-show ${s.stats.by_status.no_show ?? 0} · Cancelled ${(s.stats.by_status.cancelled_parent ?? 0) + (s.stats.by_status.cancelled_school ?? 0)}`}</Txt>
        <Txt variant="caption" raw>{s.section_labels.join(", ")}</Txt>
      </Card>
      {s.status !== "cancelled" ? (
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {s.status === "draft" ? <Button style={{ flex: 1 }} testID="ptm-publish-session" title="Publish" loading={publish.isPending} onPress={() => publish.mutate()} /> : null}
          <Button style={{ flex: 1 }} variant="outline" testID="ptm-cancel-session" title="Cancel session" onPress={() => setCancel("")} />
        </View>
      ) : null}
      {s.status !== "draft" ? (
        <View style={{ gap: spacing.sm }}>
          <SectionTitle title="Teacher availability" />
          <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ptm-admin-teacher" value={teacher} onChange={setTeacher} options={s.teachers.map((t) => ({ value: t.teacher_id, label: `${t.name} · ${t.booked}/${t.cap}${t.requests ? ` · ${t.requests} req` : ""}` }))} /></View>
          {teacher ? <StaffSlots s={s} teacherId={teacher} admin /> : null}
          <SectionTitle title={`Bookings${bk.data ? ` (${bk.data.total})` : ""}`} />
          {bk.isLoading ? <SkeletonList rows={2} /> : (bk.data?.items ?? []).map((b) => <BookingCard key={b.id} b={b} showGuardian onPress={() => router.push(`/ptm/booking/${b.id}`)} />)}
          {bk.data && !bk.data.items.length ? <Txt variant="caption">No bookings yet.</Txt> : null}
        </View>
      ) : <Txt variant="caption">Slots are generated when you publish. Draft sessions are not visible to parents or teachers.</Txt>}
      <Sheet visible={cancel !== null} onClose={() => setCancel(null)} title="Cancel session" testID="ptm-cancel-sheet" footer={<Button variant="danger" testID="ptm-cancel-confirm" title="Cancel session and notify families" disabled={(cancel ?? "").trim().length < 3} loading={doCancel.isPending} onPress={() => doCancel.mutate()} />}>
        <Field testID="ptm-cancel-reason" label="Reason (shown to families)" value={cancel ?? ""} onChangeText={setCancel} placeholder="e.g. School closed for elections" />
        <Txt variant="caption">Every confirmed booking in this session will be cancelled and parents will be notified in the app.</Txt>
      </Sheet>
    </View>
  );
}

export default function PtmSessionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const admin = can("ptm.manage");
  const q = useQuery({ queryKey: ["ptm-session", membership?.school_id, id], queryFn: () => api<PtmSession>(`/ptm/sessions/${id}`) });
  const s = q.data;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={s?.name ?? "PTM"} subtitle={s ? `${datesLabel(s)} · ${s.start_time}–${s.end_time} IST` : undefined} right={s ? <Badge testID="ptm-session-status" tone={SESSION_TONE[s.status]} label={s.status === "published" ? "Open" : s.status === "draft" ? "Draft" : "Cancelled"} /> : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.lg }}>
          {s!.status === "cancelled" ? <Card testID="ptm-cancelled-banner"><Txt variant="label" raw color={colors.error}>{`This PTM was cancelled${s!.cancel_reason ? `: ${s!.cancel_reason}` : ""}`}</Txt></Card> : null}
          <Policy s={s!} />
          {admin ? <AdminView s={s as AdminSession} /> : membership?.role === "parent" ? (s!.status === "published" ? <ParentBook s={s as ParentSession} /> : null) : membership?.role === "teacher" && s!.status === "published" ? (
            <TeacherSlots s={s!} />
          ) : null}
          {!admin && s!.status === "cancelled" ? <EmptyState icon={<CheckCircle size={32} color={colors.muted} />} title="No action needed" message="Any bookings were cancelled automatically." /> : null}
        </ScrollView>
      )}
    </View>
  );
}

function TeacherSlots({ s }: { s: PtmSession }) {
  const { membership } = useAuth();
  const me = useQuery({ queryKey: ["teacher-me", membership?.school_id], queryFn: () => api<{ teacher_id: string | null }>("/ptm/me") });
  if (me.isLoading) return <SkeletonList rows={2} />;
  if (!me.data?.teacher_id) return <ErrorState message="Teacher profile not found" onRetry={() => me.refetch()} />;
  return (
    <View style={{ gap: spacing.sm }}>
      <SectionTitle title="Your slots" />
      <Txt variant="caption">Tap a free slot to mark it unavailable, or a booked slot to open the meeting.</Txt>
      <StaffSlots s={s} teacherId={me.data.teacher_id} admin={false} />
    </View>
  );
}
