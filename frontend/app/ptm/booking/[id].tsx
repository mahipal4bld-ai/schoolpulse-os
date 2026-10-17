import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useState } from "react";
import { Linking, ScrollView, Switch, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { DateField } from "@/src/components/date-time-field";
import { Booking, BOOKING_STATUS, Slot, SlotGrid, slotWhen } from "@/src/components/ptm";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Field, Header, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate, formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

const ACTION: Record<string, string> = { booked: "Booked", rescheduled: "Rescheduled", cancelled_parent: "Cancelled by parent", cancelled_school: "Cancelled by school", completed: "Marked completed", no_show: "Marked no-show", notes: "Notes updated" };

function ParentActions({ b, refresh }: { b: Booking; refresh: () => void }) {
  const { membership } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const [moving, setMoving] = useState(false);
  const [pick, setPick] = useState<Slot | null>(null);
  const slots = useQuery({ queryKey: ["ptm-slots", membership?.school_id, b.session_id, b.teacher_id, b.student_id], enabled: moving, queryFn: () => api<{ items: Slot[] }>(`/ptm/sessions/${b.session_id}/slots?teacher_id=${b.teacher_id}&student_id=${b.student_id}`) });
  const cancel = useMutation({ mutationFn: () => api(`/ptm/bookings/${b.id}/cancel`, { method: "POST" }), onSuccess: () => { refresh(); toast.show("Booking cancelled"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const move = useMutation({ mutationFn: () => api(`/ptm/bookings/${b.id}/reschedule`, { body: { slot_id: pick!.id } }), onSuccess: () => { setMoving(false); setPick(null); refresh(); toast.show("Booking rescheduled"); }, onError: (e: Error) => { slots.refetch(); toast.show(e.message, "error"); } });
  if (b.status !== "confirmed") return null;
  return (
    <>
      {b.meeting_link ? <Button testID="ptm-join-link" title="Open meeting link" onPress={() => Linking.openURL(b.meeting_link!)} /> : null}
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <Button style={{ flex: 1 }} variant="outline" testID="ptm-reschedule" title="Reschedule" disabled={!b.can_reschedule} onPress={() => setMoving(true)} />
        <Button style={{ flex: 1 }} variant="danger" testID="ptm-cancel-booking" title="Cancel booking" disabled={!b.can_cancel} loading={cancel.isPending} onPress={() => cancel.mutate()} />
      </View>
      <Txt variant="caption" raw>{!b.can_cancel || !b.can_reschedule ? `Changes are allowed up to ${b.cancel_cutoff_hours}h (cancel) / ${b.reschedule_cutoff_hours}h (reschedule) before the meeting. Please message the teacher for anything later.` : `You can cancel up to ${b.cancel_cutoff_hours}h and reschedule up to ${b.reschedule_cutoff_hours}h before the meeting.`}</Txt>
      <Button variant="ghost" testID="ptm-open-session" title="View PTM" onPress={() => router.push(`/ptm/${b.session_id}`)} />
      <Sheet visible={moving} onClose={() => { setMoving(false); setPick(null); }} title="Choose a new time" testID="ptm-reschedule-sheet" footer={<Button testID="ptm-reschedule-confirm" title={pick ? `Move to ${slotWhen(pick.date, pick.start_time)}` : "Select a time"} disabled={!pick} loading={move.isPending} onPress={() => move.mutate()} />}>
        <Txt variant="caption">Your current booking stays in place until the new time is secured.</Txt>
        {slots.isLoading ? <SkeletonList rows={2} /> : slots.data ? <SlotGrid slots={slots.data.items.filter((x) => x.id !== b.slot_id)} selected={pick?.id} onPick={setPick} /> : null}
      </Sheet>
    </>
  );
}

function StaffActions({ b, side, refresh }: { b: Booking; side: "teacher" | "admin"; refresh: () => void }) {
  const toast = useToast();
  const [shared, setShared] = useState(b.shared_note ?? "");
  const [priv, setPriv] = useState(b.private_note ?? "");
  const [fu, setFu] = useState<{ title: string; due: string; shared: boolean } | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const done = b.status === "completed" || b.status === "no_show";
  const outcome = useMutation({ mutationFn: (status: string) => api(`/ptm/bookings/${b.id}/outcome`, { body: { status, shared_note: shared, private_note: priv } }), onSuccess: () => { refresh(); toast.show("Outcome recorded"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const notes = useMutation({ mutationFn: () => api(`/ptm/bookings/${b.id}/notes`, { method: "PATCH", body: { shared_note: shared, private_note: priv } }), onSuccess: () => { refresh(); toast.show("Notes saved"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const addFu = useMutation({ mutationFn: () => api(`/ptm/bookings/${b.id}/followups`, { body: { title: fu!.title, due_date: fu!.due || null, shared: fu!.shared } }), onSuccess: () => { setFu(null); refresh(); toast.show("Follow-up added"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const resolve = useMutation({ mutationFn: (id: string) => api(`/ptm/followups/${id}/resolve`, { method: "POST" }), onSuccess: () => refresh(), onError: (e: Error) => toast.show(e.message, "error") });
  const cancel = useMutation({ mutationFn: () => api(`/ptm/bookings/${b.id}/cancel?reason=${encodeURIComponent(reason ?? "")}`, { method: "POST" }), onSuccess: () => { setReason(null); refresh(); toast.show("Booking cancelled"); }, onError: (e: Error) => toast.show(e.message, "error") });
  return (
    <>
      {side === "teacher" && (b.status === "confirmed" || done) ? (
        <Card style={{ gap: spacing.md }}>
          <Field testID="ptm-shared-note" label="Notes shared with the guardian" value={shared} onChangeText={setShared} multiline placeholder="Factual summary and agreed next steps" />
          <Field testID="ptm-private-note" label="Private staff note (never shown to parents)" value={priv} onChangeText={setPriv} multiline placeholder="Internal context" />
          {b.status === "confirmed" ? (
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Button style={{ flex: 1 }} testID="ptm-mark-completed" title="Mark completed" loading={outcome.isPending && outcome.variables === "completed"} onPress={() => outcome.mutate("completed")} />
              <Button style={{ flex: 1 }} variant="outline" testID="ptm-mark-noshow" title="No-show" loading={outcome.isPending && outcome.variables === "no_show"} onPress={() => outcome.mutate("no_show")} />
            </View>
          ) : <Button testID="ptm-save-notes" variant="outline" title="Save notes" loading={notes.isPending} onPress={() => notes.mutate()} />}
        </Card>
      ) : null}
      {side === "admin" && b.private_note ? <Card><Txt variant="caption">Private staff note</Txt><Txt variant="body" raw>{b.private_note}</Txt></Card> : null}
      {done ? (
        <View style={{ gap: spacing.sm }}>
          <SectionTitle title="Follow-ups" action={side === "teacher" ? <Button small variant="outline" testID="ptm-add-followup" title="Add" onPress={() => setFu({ title: "", due: "", shared: false })} /> : undefined} />
          {b.followups.map((f) => (
            <Card key={f.id} style={{ gap: spacing.xs }} testID={`ptm-followup-${f.id}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <Txt variant="label" raw style={{ flex: 1 }}>{f.title}</Txt>
                <Badge tone={f.shared ? "brand" : "neutral"} label={f.shared ? "Shared" : "Staff only"} />
              </View>
              <Txt variant="caption" raw>{`${f.due_date ? `Due ${formatDate(f.due_date)} · ` : ""}${f.status === "open" ? "Open" : "Resolved"}`}</Txt>
              {f.status === "open" ? <Button small variant="ghost" testID={`ptm-resolve-${f.id}`} title="Mark resolved" onPress={() => resolve.mutate(f.id)} /> : null}
            </Card>
          ))}
          {!b.followups.length ? <Txt variant="caption">No follow-ups yet.</Txt> : null}
        </View>
      ) : null}
      {side === "admin" && b.status === "confirmed" ? <Button variant="danger" testID="ptm-admin-cancel" title="Cancel on behalf of school" onPress={() => setReason("")} /> : null}
      <Sheet visible={!!fu} onClose={() => setFu(null)} title="New follow-up" testID="ptm-followup-sheet" footer={<Button testID="ptm-followup-save" title="Add follow-up" disabled={(fu?.title.trim().length ?? 0) < 3} loading={addFu.isPending} onPress={() => addFu.mutate()} />}>
        {fu ? (
          <>
            <Field testID="ptm-followup-title" label="Task" value={fu.title} onChangeText={(title) => setFu({ ...fu, title })} placeholder="e.g. Share reading list" />
            <DateField testID="ptm-followup-due" label="Follow-up date" optional value={fu.due} onChange={(due) => setFu({ ...fu, due })} />
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Txt variant="body">Share with guardian</Txt>
              <Switch testID="ptm-followup-shared" value={fu.shared} onValueChange={(v) => setFu({ ...fu, shared: v })} />
            </View>
          </>
        ) : null}
      </Sheet>
      <Sheet visible={reason !== null} onClose={() => setReason(null)} title="Cancel booking" testID="ptm-admin-cancel-sheet" footer={<Button variant="danger" testID="ptm-admin-cancel-confirm" title="Cancel and notify parent" disabled={!(reason ?? "").trim()} loading={cancel.isPending} onPress={() => cancel.mutate()} />}>
        <Field testID="ptm-admin-cancel-reason" label="Reason (shown to the parent)" value={reason ?? ""} onChangeText={setReason} placeholder="e.g. Teacher on emergency leave" />
      </Sheet>
    </>
  );
}

export default function BookingDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const key = ["ptm-booking", membership?.school_id, id];
  const q = useQuery({ queryKey: key, queryFn: () => api<Booking>(`/ptm/bookings/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["ptm-my"] }); qc.invalidateQueries({ queryKey: ["ptm-schedule"] }); qc.invalidateQueries({ queryKey: ["ptm-slots"] }); qc.invalidateQueries({ queryKey: ["ptm-session-bookings"] }); };
  const b = q.data;
  const side = membership?.role === "parent" ? "parent" : membership?.role === "teacher" ? "teacher" : can("ptm.manage") ? "admin" : null;
  const st = b ? BOOKING_STATUS[b.status] ?? { label: b.status, tone: "neutral" as const } : null;
  const Scroll = side === "teacher" ? KeyboardAwareScrollView : ScrollView;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="PTM appointment" subtitle={b?.session_name} right={st ? <Badge testID="ptm-booking-status" tone={st.tone} label={st.label} /> : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <Scroll contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.lg }}>
          <Card style={{ gap: spacing.xs, borderLeftWidth: 4, borderLeftColor: colors.brandPrimary }} testID="ptm-booking-card">
            <Txt variant="heading" raw>{slotWhen(b!.date, b!.start_time, b!.end_time)} IST</Txt>
            <Txt variant="body" raw>{`${b!.teacher_name} · ${b!.student_name} (${b!.class_label})`}</Txt>
            {side !== "parent" && b!.guardian_name ? <Txt variant="caption" raw>{`Guardian: ${b!.guardian_name}`}</Txt> : null}
            <Txt variant="caption" raw>{b!.mode === "online" ? "Online meeting" : `In person${b!.location ? ` · ${b!.location}` : ""}`}</Txt>
            {b!.cancel_reason ? <Txt variant="caption" raw color={colors.error}>{`Reason: ${b!.cancel_reason}`}</Txt> : null}
            {b!.reschedules?.length ? <Txt variant="caption" raw>{`Rescheduled ${b!.reschedules.length} time(s)`}</Txt> : null}
          </Card>
          {side === "parent" && b!.shared_note ? <Card style={{ gap: spacing.xs }} testID="ptm-shared-note-view"><Txt variant="overline">Notes from the teacher</Txt><Txt variant="body" raw>{b!.shared_note}</Txt></Card> : null}
          {side === "parent" && b!.followups.length ? (
            <Card style={{ gap: spacing.xs }}><Txt variant="overline">Follow-ups</Txt>{b!.followups.map((f) => <Txt key={f.id} variant="body" raw>{`• ${f.title}${f.due_date ? ` (by ${formatDate(f.due_date)})` : ""}${f.status === "resolved" ? " ✓" : ""}`}</Txt>)}</Card>
          ) : null}
          {side === "parent" ? <ParentActions b={b!} refresh={refresh} /> : side ? <StaffActions key={b!.status} b={b!} side={side} refresh={refresh} /> : null}
          {side === "parent" && b!.history?.length ? (
            <View style={{ gap: spacing.xs }}><SectionTitle title="History" />{b!.history.map((h, i) => <Txt key={i} variant="caption" raw>{`${formatDateTime(h.at)} · ${ACTION[h.action] ?? h.action}`}</Txt>)}</View>
          ) : null}
        </Scroll>
      )}
    </View>
  );
}
