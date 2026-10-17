import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { View } from "react-native";

import { api } from "@/src/api";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, Field, Segmented, Txt } from "@/src/components/ui";
import { CalItem, when } from "@/src/components/calendar";
import { DateField, TimeField } from "@/src/components/date-time-field";
import { spacing } from "@/src/theme";

const CATS = ["academic", "holiday", "sports", "cultural", "meeting", "ptm", "exam", "other"] as const;
type Opt = { section_id: string; label: string };
const label = (c: string) => (c === "ptm" ? "PTM" : c[0].toUpperCase() + c.slice(1));

/** Client-side checks mirror the server rules (server stays authoritative). */
function problems(f: { start: string; end: string; startTime: string; endTime: string }) {
  const e: Record<string, string> = {};
  if (!f.start) e.start = "Choose a start date";
  if (f.end && f.end < f.start) e.end = "End date must be on or after the start date";
  if (f.endTime && !f.startTime) e.startTime = "Add a start time before an end time";
  if (f.startTime && f.endTime && (!f.end || f.end === f.start) && f.endTime <= f.startTime) e.endTime = "End time must be after the start time";
  return e;
}

/** Leader-only sheet to create (draft/publish) or edit an event. */
export function EventForm({ visible, day, onClose, initial }: { visible: boolean; day: string; onClose: () => void; initial?: CalItem | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const secs = useQuery({ queryKey: ["homework-options"], enabled: visible, queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const blank = { title: "", description: "", category: "academic" as (typeof CATS)[number], start: day, end: "", startTime: "", endTime: "", location: "", scope: "school" as "school" | "sections", sections: [] as string[] };
  const [f, setF] = useState(blank);
  React.useEffect(() => {
    if (!visible) return;
    setF(initial ? { ...blank, title: initial.title, description: initial.description, category: initial.category as (typeof CATS)[number], start: initial.start_date, end: initial.end_date === initial.start_date ? "" : initial.end_date, startTime: initial.start_time ?? "", endTime: initial.end_time ?? "", location: initial.location } : { ...blank, start: day });
  }, [visible]);  // eslint-disable-line react-hooks/exhaustive-deps
  const errs = problems(f);
  const bad = Object.keys(errs).length > 0;
  const save = useMutation({
    mutationFn: (action: "draft" | "publish") => (initial
      ? api<CalItem>(`/events/${initial.id}`, { method: "PATCH", body: { title: f.title, description: f.description, location: f.location, start_date: f.start, end_date: f.end || f.start, start_time: f.startTime || null, end_time: f.endTime || null } })
      : api<CalItem>("/events", { body: { title: f.title, description: f.description, category: f.category, start_date: f.start, end_date: f.end || null, start_time: f.startTime || null, end_time: f.endTime || null, location: f.location, audience: { scope: f.scope, section_ids: f.scope === "sections" ? f.sections : [] }, action } })),
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ["calendar"] }); onClose(); toast.show(initial ? "Event updated" : e.status === "published" ? "Event published" : "Draft saved"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <Sheet visible={visible} onClose={onClose} title={initial ? "Edit event" : "New event"} testID="event-sheet" footer={
      initial ? <Button testID="event-save-edit" title="Save changes" disabled={bad} loading={save.isPending} onPress={() => save.mutate("draft")} /> : (
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <Button style={{ flex: 1 }} variant="outline" testID="event-save-draft" title="Save draft" disabled={bad} loading={save.isPending && save.variables === "draft"} onPress={() => save.mutate("draft")} />
        <Button style={{ flex: 1 }} testID="event-publish" title="Publish" disabled={bad} loading={save.isPending && save.variables === "publish"} onPress={() => save.mutate("publish")} />
      </View>)
    }>
      <Field testID="event-title-input" label="Title" value={f.title} onChangeText={(title) => setF({ ...f, title })} placeholder="e.g. Annual Day rehearsal" />
      {initial ? null : <View style={{ marginHorizontal: -spacing.lg }}>
        <ChipRow testIDPrefix="event-cat" value={f.category} onChange={(category) => setF({ ...f, category })} options={CATS.map((c) => ({ value: c, label: label(c) }))} />
      </View>}
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <View style={{ flex: 1 }}><DateField testID="event-start-input" label="Start date" value={f.start} error={errs.start} onChange={(start) => setF({ ...f, start })} /></View>
        <View style={{ flex: 1 }}><DateField testID="event-end-input" label="End date" optional value={f.end} min={f.start} error={errs.end} onChange={(end) => setF({ ...f, end })} /></View>
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <View style={{ flex: 1 }}><TimeField testID="event-start-time-input" label="Start time" optional value={f.startTime} error={errs.startTime} onChange={(startTime) => setF({ ...f, startTime })} /></View>
        <View style={{ flex: 1 }}><TimeField testID="event-end-time-input" label="End time" optional value={f.endTime} error={errs.endTime} onChange={(endTime) => setF({ ...f, endTime })} /></View>
      </View>
      <Field testID="event-location-input" label="Location (optional)" value={f.location} onChangeText={(location) => setF({ ...f, location })} placeholder="e.g. Auditorium" />
      <Field testID="event-desc-input" label="Details (optional)" value={f.description} onChangeText={(description) => setF({ ...f, description })} multiline placeholder="What families should know" />
      {initial ? null : <Segmented testIDPrefix="event-scope" value={f.scope} onChange={(scope) => setF({ ...f, scope })} options={[{ value: "school", label: "Whole school" }, { value: "sections", label: "Sections" }]} />}
      {!initial && f.scope === "sections" ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {(secs.data?.items ?? []).map((s) => {
            const on = f.sections.includes(s.section_id);
            return <Button key={s.section_id} small variant={on ? "primary" : "outline"} testID={`event-sec-${s.section_id}`} title={s.label} onPress={() => setF({ ...f, sections: on ? f.sections.filter((x) => x !== s.section_id) : [...f.sections, s.section_id] })} />;
          })}
        </View>
      ) : null}
    </Sheet>
  );
}

/** Event / exam detail with leader actions (publish draft, cancel with reason). */
export function EventDetail({ item, manager, onClose, onEdit, onOpenPtm }: { item: CalItem | null; manager: boolean; onClose: () => void; onEdit: (i: CalItem) => void; onOpenPtm: (i: CalItem) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [reason, setReason] = useState("");
  React.useEffect(() => setReason(""), [item?.id]);
  const act = useMutation({
    mutationFn: (a: "publish" | "cancel") => api(`/events/${item!.id}/action?act=${a}${a === "cancel" && reason ? `&reason=${encodeURIComponent(reason)}` : ""}`, { method: "POST" }),
    onSuccess: (_d, a) => { qc.invalidateQueries({ queryKey: ["calendar"] }); onClose(); toast.show(a === "publish" ? "Event published" : "Event cancelled"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const canAct = manager && item?.kind === "event" && item.status !== "cancelled";
  return (
    <Sheet visible={!!item} onClose={onClose} title={item?.title ?? ""} testID="event-detail-sheet" footer={canAct ? (
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <Button style={{ flex: 1 }} variant="outline" testID="event-cancel" title="Cancel event" loading={act.isPending && act.variables === "cancel"} onPress={() => act.mutate("cancel")} />
        <Button style={{ flex: 1 }} variant="outline" testID="event-edit" title="Edit" onPress={() => onEdit(item!)} />
        {item?.status === "draft" ? <Button style={{ flex: 1 }} testID="event-detail-publish" title="Publish" loading={act.isPending && act.variables === "publish"} onPress={() => act.mutate("publish")} /> : null}
      </View>
    ) : item?.kind === "ptm" && item.status !== "cancelled" ? <Button testID="event-open-ptm" title="Open PTM" onPress={() => onOpenPtm(item)} /> : undefined}>
      {item ? (
        <View style={{ gap: spacing.sm }}>
          <Txt variant="label" raw testID="event-detail-when">{when(item)}</Txt>
          {item.location ? <Txt variant="body" raw>{item.location}</Txt> : null}
          {item.status === "cancelled" ? <Txt variant="body" raw testID="event-detail-cancelled">Cancelled{item.cancel_reason ? `: ${item.cancel_reason}` : ""}</Txt> : null}
          {item.description ? <Txt variant="body" raw>{item.description}</Txt> : null}
          {item.papers?.length ? item.papers.map((p) => <Txt key={p.subject + p.date} variant="body" raw>{p.date} · {p.subject}</Txt>) : null}
          {canAct && item.status === "published" ? <Field testID="event-cancel-reason" label="Reason (shown to families if cancelled)" value={reason} onChangeText={setReason} placeholder="e.g. Heavy rain forecast" /> : null}
        </View>
      ) : null}
    </Sheet>
  );
}
