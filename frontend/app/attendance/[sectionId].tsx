import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { ChartBar, CheckCircle } from "phosphor-react-native";
import React, { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate, formatDateTime, initials } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

type Status = "present" | "absent" | "late";
type SheetData = {
  section: { id: string; label: string };
  date: string;
  submitted: boolean;
  submitted_at: string | null;
  corrections: number;
  students: { id: string; name: string; roll_no?: number; admission_no: string; status: Status | null }[];
};
const NEXT: Record<Status, Status> = { present: "absent", absent: "late", late: "present" };
const LABEL: Record<Status, string> = { present: "P", absent: "A", late: "L" };

export default function AttendanceScreen() {
  const { sectionId } = useLocalSearchParams<{ sectionId: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["attendance", membership?.school_id, sectionId];
  const q = useQuery({ queryKey: key, queryFn: () => api<SheetData>(`/attendance/sections/${sectionId}`) });
  const [marks, setMarks] = useState<Record<string, Status>>({});
  const [reason, setReason] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
  const report = useQuery({
    queryKey: ["att-report", membership?.school_id, sectionId],
    enabled: reportOpen,
    queryFn: () => api<{ month: string; working_days: number; rows: { student_id: string; name: string; present: number; absent: number; late: number; rate: number | null }[] }>(`/attendance/reports/monthly?section_id=${sectionId}`),
  });

  useEffect(() => {
    if (q.data) setMarks(Object.fromEntries(q.data.students.map((s) => [s.id, s.status ?? "present"])));
  }, [q.data]);

  const changed = useMemo(() => !!q.data?.submitted && q.data.students.some((s) => s.status !== marks[s.id]), [q.data, marks]);
  const counts = useMemo(() => {
    const c = { present: 0, absent: 0, late: 0 };
    Object.values(marks).forEach((m) => (c[m] += 1));
    return c;
  }, [marks]);

  const submit = useMutation({
    mutationFn: () => api<SheetData>(`/attendance/sections/${sectionId}`, { method: "PUT", body: { records: Object.entries(marks).map(([student_id, status]) => ({ student_id, status })), reason: reason || null } }),
    onSuccess: (d) => {
      qc.setQueryData(key, d);
      qc.invalidateQueries({ queryKey: ["teacher-dash"] });
      qc.invalidateQueries({ queryKey: ["att-today"] });
      setReason("");
      toast.show(d.corrections && changed ? "Attendance corrected" : "Attendance submitted");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  const tone = (s: Status) => (s === "present" ? [colors.successSoft, "#047857"] : s === "absent" ? [colors.errorSoft, colors.error] : [colors.warningSoft, "#B45309"]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header
        back
        title={q.data?.section.label ?? "Attendance"}
        subtitle={q.data ? formatDate(q.data.date) : undefined}
        right={<Pressable testID="attendance-report-button" onPress={() => setReportOpen(true)} hitSlop={8} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><ChartBar size={22} color={colors.brandPrimary} /></Pressable>}
      />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="attendance-list"
          data={q.data!.students}
          keyExtractor={(s) => s.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 200, gap: spacing.sm }}
          ListHeaderComponent={
            <View style={{ gap: spacing.md, marginBottom: spacing.sm }}>
              <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center" }}>
                {q.data!.submitted ? <Badge testID="attendance-submitted-badge" tone="success" label="Submitted" /> : <Badge testID="attendance-pending-badge" tone="warning" label="Not submitted" />}
                {q.data!.submitted_at ? <Txt variant="caption">{formatDateTime(q.data!.submitted_at)}</Txt> : null}
                <View style={{ flex: 1 }} />
                <Txt variant="caption" testID="attendance-counts">P {counts.present} · A {counts.absent} · L {counts.late}</Txt>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Button small style={{ flex: 1 }} variant="outline" testID="mark-all-present" title="All present" icon={<CheckCircle size={16} color={colors.onSurface} />} onPress={() => setMarks(Object.fromEntries(Object.keys(marks).map((k) => [k, "present"])))} />
              </View>
              <Txt variant="caption">Tap a student to change: present → absent → late</Txt>
            </View>
          }
          renderItem={({ item }) => {
            const s = marks[item.id] ?? "present";
            const [bg, fg] = tone(s);
            return (
              <Pressable
                testID={`attendance-row-${item.admission_no}`}
                onPress={() => {
                  Haptics.selectionAsync().catch(() => {});
                  setMarks((m) => ({ ...m, [item.id]: NEXT[s] }));
                }}
                style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, minHeight: 60, opacity: pressed ? 0.85 : 1 })}
              >
                <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="caption" raw color={colors.onBrandTertiary}>{initials(item.name)}</Txt>
                </View>
                <View style={{ flex: 1 }}>
                  <Txt variant="label" raw numberOfLines={1}>{item.roll_no ? `${item.roll_no}. ` : ""}{item.name}</Txt>
                  <Txt variant="caption" raw>{item.admission_no}</Txt>
                </View>
                <View testID={`attendance-status-${item.admission_no}`} style={{ width: 44, height: 36, borderRadius: radius.sm + 2, backgroundColor: bg, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="label" raw color={fg}>{LABEL[s]}</Txt>
                </View>
              </Pressable>
            );
          }}
        />
      )}
      {q.data ? (
        <KeyboardStickyView offset={{ opened: insets.bottom }} style={{ position: "absolute", left: 0, right: 0, bottom: 0 }}>
          <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.sm }}>
            {changed ? <Field testID="attendance-reason-input" label="Reason for correction" value={reason} onChangeText={setReason} placeholder="e.g. Arrived late, marked by mistake" /> : null}
            <Button testID="attendance-submit-button" title={q.data.submitted ? "Save correction" : "Submit attendance"} disabled={q.data.submitted && !changed} loading={submit.isPending} onPress={() => submit.mutate()} />
          </View>
        </KeyboardStickyView>
      ) : null}
      <Sheet visible={reportOpen} onClose={() => setReportOpen(false)} title="Monthly report" testID="attendance-report-sheet">
        {report.isLoading ? <SkeletonList rows={3} /> : report.data ? (
          <View style={{ gap: spacing.sm }}>
            <Txt variant="caption" raw>{report.data.month} · {report.data.working_days} days</Txt>
            {report.data.rows.map((r) => (
              <View key={r.student_id} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.xs }}>
                <Txt variant="body" raw style={{ flex: 1 }} numberOfLines={1}>{r.name}</Txt>
                <Txt variant="caption" raw>P {r.present} · A {r.absent} · L {r.late} · {r.rate ?? "—"}%</Txt>
              </View>
            ))}
          </View>
        ) : null}
      </Sheet>
    </View>
  );
}
