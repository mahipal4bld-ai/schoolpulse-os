import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { View } from "react-native";

import { api } from "@/src/api";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, Field, Segmented, Txt } from "@/src/components/ui";
import { CalItem, when } from "@/src/components/calendar";
import { spacing } from "@/src/theme";

const CATS = ["academic", "holiday", "sports", "cultural", "meeting", "ptm", "exam", "other"] as const;
type Opt = { section_id: string; label: string };
const label = (c: string) => (c === "ptm" ? "PTM" : c[0].toUpperCase() + c.slice(1));

/** Leader-only sheet to create an event (draft or publish). */
export function EventForm({ visible, day, onClose }: { visible: boolean; day: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const secs = useQuery({ queryKey: ["homework-options"], enabled: visible, queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const blank = { title: "", description: "", category: "academic" as (typeof CATS)[number], start: day, end: "", startTime: "", endTime: "", location: "", scope: "school" as "school" | "sections", sections: [] as string[] };
  const [f, setF] = useState(blank);
  React.useEffect(() => { if (visible) setF({ ...blank, start: day }); }, [visible]);  // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: (action: "draft" | "publish") => api<CalItem>("/events", { body: { title: f.title, description: f.description, category: f.category, start_date: f.start, end_date: f.end || null, start_time: f.startTime || null, end_time: f.endTime || null, location: f.location, audience: { scope: f.scope, section_ids: f.scope === "sections" ? f.sections : [] }, action } }),
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ["calendar"] }); onClose(); toast.show(e.status === "published" ? "Event published" : "Draft saved"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <Sheet visible={visible} onClose={onClose} title="New event" testID="event-sheet" footer={
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <Button style={{ flex: 1 }} variant="outline" testID="event-save-draft" title="Save draft" loading={save.isPending && save.variables === "draft"} onPress={() => save.mutate("draft")} />
        <Button style={{ flex: 1 }} testID="event-publish" title="Publish" loading={save.isPending && save.variables === "publish"} onPress={() => save.mutate("publish")} />
      </View>
    }>
      <Field testID="event-title-input" label="Title" value={f.title} onChangeText={(title) => setF({ ...f, title })} placeholder="e.g. Annual Day rehearsal" />
      <View style={{ marginHorizontal: -spacing.lg }}>
        <ChipRow testIDPrefix="event-cat" value={f.category} onChange={(category) => setF({ ...f, category })} options={CATS.map((c) => ({ value: c, label: label(c) }))} />
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <View style={{ flex: 1 }}><Field testID="event-start-input" label="Start date" value={f.start} onChangeText={(start) => setF({ ...f, start })} autoCapitalize="none" placeholder="YYYY-MM-DD" /></View>
        <View style={{ flex: 1 }}><Field testID="event-end-input" label="End date (optional)" value={f.end} onChangeText={(end) => setF({ ...f, end })} autoCapitalize="none" placeholder="Same day" /></View>
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <View style={{ flex: 1 }}><Field testID="event-start-time-input" label="Start time" value={f.startTime} onChangeText={(startTime) => setF({ ...f, startTime })} autoCapitalize="none" placeholder="HH:MM" /></View>
        <View style={{ flex: 1 }}><Field testID="event-end-time-input" label="End time" value={f.endTime} onChangeText={(endTime) => setF({ ...f, endTime })} autoCapitalize="none" placeholder="HH:MM" /></View>
      </View>
      <Field testID="event-location-input" label="Location (optional)" value={f.location} onChangeText={(location) => setF({ ...f, location })} placeholder="e.g. Auditorium" />
      <Field testID="event-desc-input" label="Details (optional)" value={f.description} onChangeText={(description) => setF({ ...f, description })} multiline placeholder="What families should know" />
      <Segmented testIDPrefix="event-scope" value={f.scope} onChange={(scope) => setF({ ...f, scope })} options={[{ value: "school", label: "Whole school" }, { value: "sections", label: "Sections" }]} />
      {f.scope === "sections" ? (
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
export function EventDetail({ item, manager, onClose }: { item: CalItem | null; manager: boolean; onClose: () => void }) {
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
        {item?.status === "draft" ? <Button style={{ flex: 1 }} testID="event-detail-publish" title="Publish" loading={act.isPending && act.variables === "publish"} onPress={() => act.mutate("publish")} /> : null}
      </View>
    ) : undefined}>
      {item ? (
        <View style={{ gap: spacing.sm }}>
          <Txt variant="label" raw testID="event-detail-when">{when(item)}</Txt>
          {item.location ? <Txt variant="body" raw>📍 {item.location}</Txt> : null}
          {item.status === "cancelled" ? <Txt variant="body" raw testID="event-detail-cancelled">Cancelled{item.cancel_reason ? `: ${item.cancel_reason}` : ""}</Txt> : null}
          {item.description ? <Txt variant="body" raw>{item.description}</Txt> : null}
          {item.papers?.length ? item.papers.map((p) => <Txt key={p.subject + p.date} variant="body" raw>{p.date} · {p.subject}</Txt>) : null}
          {canAct && item.status === "published" ? <Field testID="event-cancel-reason" label="Reason (shown to families if cancelled)" value={reason} onChangeText={setReason} placeholder="e.g. Heavy rain forecast" /> : null}
        </View>
      ) : null}
    </Sheet>
  );
}
