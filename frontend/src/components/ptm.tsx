import { useQuery } from "@tanstack/react-query";
import React from "react";
import { Pressable, View } from "react-native";

import { api } from "@/src/api";
import { timeLabel } from "@/src/components/date-time-field";
import { Badge, Card, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export type PtmSession = {
  id: string; name: string; status: "draft" | "publishing" | "published" | "cancelled"; publish_error?: string | null; dates: string[]; start_time: string; end_time: string;
  slot_minutes: number; break_minutes: number; capacity: number; mode: "physical" | "online"; location: string; meeting_link?: string;
  cancel_cutoff_hours: number; reschedule_cutoff_hours: number; max_per_child: number; cancel_reason?: string | null;
  booking_opens_at?: string | null; booking_closes_at?: string | null; section_ids: string[]; teacher_ids: string[];
  capacity_total?: number; booked_total?: number;
};
export type Slot = { id: string; date: string; start_time: string; end_time: string; available: boolean; status?: string; booked?: number; capacity?: number; block_reason?: string | null; bookings?: { booking_id: string; status: string; guardian_name: string; student_name: string; class_label: string }[] };
export type Followup = { id: string; title: string; due_date: string | null; shared: boolean; status: "open" | "resolved" };
export type Booking = {
  id: string; session_id: string; slot_id: string; teacher_id: string; student_id: string; status: string; date: string; start_time: string; end_time: string;
  session_name: string; teacher_name: string; student_name: string; class_label: string; guardian_name?: string; mode: string; location: string;
  meeting_link?: string; can_cancel?: boolean; can_reschedule?: boolean; cancel_cutoff_hours?: number; reschedule_cutoff_hours?: number;
  cancel_reason?: string | null; shared_note: string; private_note?: string; followups: Followup[]; reschedules: unknown[]; history?: { at: string; action: string }[];
};

export const BOOKING_STATUS: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "brand" | "error" }> = {
  confirmed: { label: "Confirmed", tone: "brand" },
  completed: { label: "Completed", tone: "success" },
  no_show: { label: "No-show", tone: "warning" },
  cancelled_parent: { label: "Cancelled by parent", tone: "error" },
  cancelled_school: { label: "Cancelled by school", tone: "error" },
};
export const SESSION_TONE = { draft: "warning", publishing: "warning", published: "success", cancelled: "error" } as const;
export const SESSION_LABEL = { draft: "Draft", publishing: "Publishing incomplete", published: "Open", cancelled: "Cancelled" } as const;
export const slotWhen = (d: string, a: string, b?: string) => `${formatDate(d)} · ${timeLabel(a)}${b ? ` – ${timeLabel(b)}` : ""}`;
export const datesLabel = (s: PtmSession) => s.dates.map(formatDate).join(", ");

export function BookingCard({ b, onPress, showGuardian }: { b: Booking; onPress: () => void; showGuardian?: boolean }) {
  const st = BOOKING_STATUS[b.status] ?? { label: b.status, tone: "neutral" as const };
  return (
    <Pressable testID={`ptm-booking-${b.id}`} onPress={onPress} accessibilityRole="button">
      <Card style={{ gap: spacing.xs }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <Txt variant="caption" raw style={{ flex: 1 }}>{slotWhen(b.date, b.start_time, b.end_time)}</Txt>
          <Badge tone={st.tone} label={st.label} />
          {b.reschedules?.length ? <Badge tone="neutral" label="Rescheduled" /> : null}
        </View>
        <Txt variant="label" raw>{showGuardian ? `${b.student_name} · ${b.guardian_name ?? ""}` : `${b.teacher_name} · ${b.student_name}`}</Txt>
        <Txt variant="caption" raw>{b.session_name} · {b.class_label}</Txt>
      </Card>
    </Pressable>
  );
}

/** Grouped slot picker (by date). `onPick` only fires for selectable slots. */
export function SlotGrid({ slots, selected, onPick, staff }: { slots: Slot[]; selected?: string | null; onPick: (s: Slot) => void; staff?: boolean }) {
  const { colors } = useTheme();
  const days = [...new Set(slots.map((s) => s.date))];
  return (
    <View style={{ gap: spacing.md }}>
      {days.map((d) => (
        <View key={d} style={{ gap: spacing.sm }}>
          <Txt variant="overline" raw>{formatDate(d)}</Txt>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {slots.filter((s) => s.date === d).map((s) => {
              const on = selected === s.id;
              const blocked = staff && s.status !== "available";
              const full = staff ? (s.booked ?? 0) >= (s.capacity ?? 1) : !s.available;
              const bg = on ? colors.brandPrimary : blocked ? colors.surfaceTertiary : full ? (staff ? colors.brandTertiary : colors.surfaceTertiary) : colors.surface;
              return (
                <Pressable key={s.id} testID={`ptm-slot-${s.id}`} disabled={!staff && !s.available} onPress={() => onPick(s)}
                  accessibilityRole="button" accessibilityState={{ disabled: !staff && !s.available, selected: on }}
                  accessibilityLabel={`${timeLabel(s.start_time)} ${s.available ? "available" : blocked ? "unavailable" : "booked"}`}
                  style={{ minWidth: 92, minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.md, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: on ? colors.brandPrimary : colors.border, backgroundColor: bg, opacity: !staff && !s.available ? 0.5 : 1 }}>
                  <Txt variant="label" raw color={on ? colors.onBrandPrimary : colors.onSurface} style={!staff && !s.available ? { textDecorationLine: "line-through" } : undefined}>{timeLabel(s.start_time)}</Txt>
                  {staff ? <Txt variant="caption" raw color={on ? colors.onBrandPrimary : colors.onSurfaceTertiary}>{blocked ? (s.status === "block_requested" ? "Requested" : "Blocked") : `${s.booked}/${s.capacity}`}</Txt> : null}
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}
    </View>
  );
}

export type Insights = { sessions: number; live_sessions: number; eligible_households: number; booked: number; available: number; capacity: number; utilization: number; completed: number; no_show: number; cancelled: number; followups_pending: number; by_class: { class_name: string; bookings: number }[]; by_teacher: { teacher_id: string; name: string; bookings: number }[] };

export function useInsights(schoolId: string | undefined, qs: string, enabled = true) {
  return useQuery({ queryKey: ["ptm-insights", schoolId, qs], enabled, queryFn: () => api<Insights>(`/ptm/insights${qs ? `?${qs}` : ""}`) });
}

function Stat({ label, value, testID }: { label: string; value: string | number; testID: string }) {
  return (
    <Card style={{ flexBasis: "30%", flexGrow: 1, gap: 2, padding: spacing.md }} testID={testID}>
      <Txt variant="heading" raw testID={`${testID}-value`}>{String(value)}</Txt>
      <Txt variant="caption">{label}</Txt>
    </Card>
  );
}

export function InsightsPanel({ d }: { d: Insights }) {
  const { colors } = useTheme();
  const max = Math.max(1, ...d.by_class.map((c) => c.bookings));
  return (
    <View style={{ gap: spacing.md }} testID="ptm-insights">
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
        <Stat testID="ins-sessions" label="Sessions" value={d.sessions} />
        <Stat testID="ins-households" label="Eligible households" value={d.eligible_households} />
        <Stat testID="ins-booked" label="Booked" value={d.booked} />
        <Stat testID="ins-available" label="Open seats" value={d.available} />
        <Stat testID="ins-utilization" label="Utilization" value={`${Math.round(d.utilization * 100)}%`} />
        <Stat testID="ins-completed" label="Completed" value={d.completed} />
        <Stat testID="ins-cancelled" label="Cancelled" value={d.cancelled} />
        <Stat testID="ins-noshow" label="No-shows" value={d.no_show} />
        <Stat testID="ins-followups" label="Follow-ups pending" value={d.followups_pending} />
      </View>
      {d.by_class.length ? (
        <Card style={{ gap: spacing.sm }} testID="ins-by-class">
          <Txt variant="overline">Bookings by class</Txt>
          {d.by_class.map((c) => (
            <View key={c.class_name} style={{ gap: 4 }}>
              <View style={{ flexDirection: "row" }}><Txt variant="caption" raw style={{ flex: 1 }}>{c.class_name}</Txt><Txt variant="caption" raw>{String(c.bookings)}</Txt></View>
              <View style={{ height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary }}><View style={{ width: `${(c.bookings / max) * 100}%`, height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary }} /></View>
            </View>
          ))}
        </Card>
      ) : null}
      {d.by_teacher.length ? (
        <Card style={{ gap: spacing.xs }} testID="ins-by-teacher">
          <Txt variant="overline">Bookings by teacher</Txt>
          {d.by_teacher.map((t) => <View key={t.teacher_id} style={{ flexDirection: "row" }}><Txt variant="body" raw style={{ flex: 1 }}>{t.name}</Txt><Txt variant="label" raw>{String(t.bookings)}</Txt></View>)}
        </Card>
      ) : null}
      <Txt variant="caption">Booked counts confirmed, completed and no-show meetings. Utilization is booked seats divided by bookable seats.</Txt>
    </View>
  );
}
