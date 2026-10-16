import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { CalendarCheck } from "phosphor-react-native";
import React, { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Badge, Button, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate, formatDateTime, initials } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

export type StaffStatus = "present" | "absent" | "late" | "half_day" | "on_leave";
type Reg = {
  date: string;
  unmarked: number;
  counts: Record<StaffStatus, number>;
  rows: { teacher_id: string; name: string; designation: string; employee_code: string; status: StaffStatus | null; source: string | null; check_in_at: string | null; leave_type: string | null }[];
};
const CYCLE: StaffStatus[] = ["present", "absent", "late", "half_day", "on_leave"];
export const STAFF_LABEL: Record<StaffStatus, string> = { present: "P", absent: "A", late: "L", half_day: "½", on_leave: "LV" };

export default function StaffAttendance() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const key = ["staff-reg", membership?.school_id];
  const q = useQuery({ queryKey: key, queryFn: () => api<Reg>("/staff/attendance") });
  const [marks, setMarks] = useState<Record<string, StaffStatus>>({});
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (q.data) setMarks(Object.fromEntries(q.data.rows.map((r) => [r.teacher_id, r.status ?? "present"])));
  }, [q.data]);

  const changedRecorded = useMemo(() => !!q.data?.rows.some((r) => r.status && r.source !== "leave" && r.status !== marks[r.teacher_id]), [q.data, marks]);
  const dirty = useMemo(() => !!q.data?.rows.some((r) => r.status !== marks[r.teacher_id]), [q.data, marks]);

  const save = useMutation({
    mutationFn: () => api<Reg>("/staff/attendance", { method: "PUT", body: { records: Object.entries(marks).map(([teacher_id, status]) => ({ teacher_id, status })), reason: reason || null } }),
    onSuccess: (d) => {
      qc.setQueryData(key, d);
      qc.invalidateQueries({ queryKey: ["staff-today"] });
      setReason("");
      toast.show("Staff attendance saved");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  const tone = (s: StaffStatus) =>
    s === "present" ? [colors.successSoft, "#047857"] : s === "absent" ? [colors.errorSoft, colors.error] : s === "on_leave" ? [colors.brandTertiary, colors.onBrandTertiary] : [colors.warningSoft, "#B45309"];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header
        back
        title="Staff attendance"
        subtitle={q.data ? formatDate(q.data.date) : undefined}
        right={can("leave.approve") || can("staff.manage") ? <Pressable testID="open-leave-approvals" onPress={() => router.push("/leave-approvals")} hitSlop={8} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><CalendarCheck size={22} color={colors.brandPrimary} /></Pressable> : undefined}
      />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="staff-register-list"
          data={q.data!.rows}
          keyExtractor={(r) => r.teacher_id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 200, gap: spacing.sm }}
          ListHeaderComponent={
            <View style={{ gap: spacing.sm, marginBottom: spacing.sm }}>
              <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                {q.data!.unmarked ? <Badge testID="staff-unmarked-badge" tone="warning" label={`${q.data!.unmarked} not marked`} /> : <Badge testID="staff-complete-badge" tone="success" label="All marked" />}
                <Badge tone="brand" label={`On leave ${q.data!.counts.on_leave}`} />
              </View>
              <Txt variant="caption">Tap to change: P → A → L → ½ day → Leave. Self check-ins show their time.</Txt>
            </View>
          }
          renderItem={({ item }) => {
            const s = marks[item.teacher_id] ?? "present";
            const [bg, fg] = tone(s);
            return (
              <Pressable
                testID={`staff-row-${item.teacher_id}`}
                onPress={() => {
                  Haptics.selectionAsync().catch(() => {});
                  setMarks((m) => ({ ...m, [item.teacher_id]: CYCLE[(CYCLE.indexOf(s) + 1) % CYCLE.length] }));
                }}
                style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, minHeight: 60, opacity: pressed ? 0.85 : 1 })}
              >
                <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="caption" raw color={colors.onBrandTertiary}>{initials(item.name)}</Txt>
                </View>
                <View style={{ flex: 1 }}>
                  <Txt variant="label" raw numberOfLines={1}>{item.name}</Txt>
                  <Txt variant="caption" raw numberOfLines={1}>
                    {item.designation}
                    {item.check_in_at ? ` · In ${formatDateTime(item.check_in_at)}` : item.leave_type ? ` · ${item.leave_type} leave` : ""}
                  </Txt>
                </View>
                <View testID={`staff-status-${item.teacher_id}`} style={{ minWidth: 44, height: 36, paddingHorizontal: 6, borderRadius: radius.sm + 2, backgroundColor: bg, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="label" raw color={fg}>{STAFF_LABEL[s]}</Txt>
                </View>
              </Pressable>
            );
          }}
        />
      )}
      {q.data ? (
        <KeyboardStickyView offset={{ opened: insets.bottom }} style={{ position: "absolute", left: 0, right: 0, bottom: 0 }}>
          <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.sm }}>
            {changedRecorded ? <Field testID="staff-reason-input" label="Reason for change" value={reason} onChangeText={setReason} placeholder="e.g. Left early, marked by mistake" /> : null}
            <Button testID="staff-save-button" title="Save register" disabled={!dirty && !q.data.unmarked} loading={save.isPending} onPress={() => save.mutate()} />
          </View>
        </KeyboardStickyView>
      ) : null}
    </View>
  );
}
