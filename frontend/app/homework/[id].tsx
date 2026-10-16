import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Trash } from "phosphor-react-native";
import React, { useEffect, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { AttachmentList, Completion, Homework } from "@/src/components/homework";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Header, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

const NEXT: Record<Completion, Completion> = { done: "not_done", not_done: "late", late: "done" };
const LABEL: Record<Completion, string> = { done: "Done", not_done: "Not done", late: "Late" };

export default function HomeworkDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const key = ["homework-item", membership?.school_id, id];
  const q = useQuery({ queryKey: key, queryFn: () => api<Homework>(`/homework/${id}`) });
  const [marks, setMarks] = useState<Record<string, Completion>>({});
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (q.data?.students) setMarks(Object.fromEntries(q.data.students.filter((s) => s.status).map((s) => [s.id, s.status as Completion])));
  }, [q.data]);
  const after = (d: Homework, msg: string) => {
    qc.setQueryData(key, d);
    qc.invalidateQueries({ queryKey: ["homework"] });
    toast.show(msg);
  };
  const publish = useMutation({ mutationFn: () => api<Homework>(`/homework/${id}/publish`, { method: "POST" }), onSuccess: (d) => after(d, "Published to parents"), onError: (e: Error) => toast.show(e.message, "error") });
  const saveComp = useMutation({
    mutationFn: () => api<Homework>(`/homework/${id}/completion`, { method: "PUT", body: { records: Object.entries(marks).map(([student_id, status]) => ({ student_id, status })) } }),
    onSuccess: (d) => after(d, "Completion saved"),
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const del = useMutation({
    mutationFn: () => api(`/homework/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["homework"] });
      toast.show("Homework deleted");
      router.back();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const h = q.data;
  const dirty = !!h?.students?.some((s) => (marks[s.id] ?? null) !== s.status);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header
        back
        title={h?.subject_name ?? "Homework"}
        subtitle={h?.section_label}
        right={h ? <Pressable testID="hw-delete-button" onPress={() => setConfirm(true)} hitSlop={8} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}><Trash size={20} color={colors.muted} /></Pressable> : undefined}
      />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : h ? (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
          <Card style={{ gap: spacing.sm }} testID="hw-detail-card">
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Badge testID="hw-status-badge" tone={h.status === "published" ? "success" : "neutral"} label={h.status} />
              <Badge tone="brand" label={`Due ${formatDate(h.due_date)}`} />
            </View>
            <Txt variant="heading" raw>{h.title}</Txt>
            {h.description ? <Txt variant="body" raw>{h.description}</Txt> : null}
            <Txt variant="caption" raw>Assigned {formatDate(h.assigned_date)}</Txt>
            <AttachmentList items={h.attachments} />
          </Card>
          {h.status === "published" && h.students?.length ? (
            <View>
              <SectionTitle title={`Completion · ${h.completion_counts?.done ?? 0}/${h.students.length} done`} action={<Pressable testID="hw-mark-all-done" onPress={() => setMarks(Object.fromEntries(h.students!.map((s) => [s.id, "done" as Completion])))} hitSlop={8}><Txt variant="label" color={colors.brandPrimary}>All done</Txt></Pressable>} />
              <Card style={{ paddingVertical: spacing.xs, gap: 0 }}>
                {h.students.map((s, i) => {
                  const m = marks[s.id];
                  const tone = m === "done" ? [colors.successSoft, "#047857"] : m === "late" ? [colors.warningSoft, "#B45309"] : m === "not_done" ? [colors.errorSoft, colors.error] : [colors.surfaceTertiary, colors.onSurfaceTertiary];
                  return (
                    <Pressable
                      key={s.id}
                      testID={`hw-student-${s.id}`}
                      onPress={() => {
                        Haptics.selectionAsync().catch(() => {});
                        setMarks((x) => ({ ...x, [s.id]: m ? NEXT[m] : "done" }));
                      }}
                      style={{ flexDirection: "row", alignItems: "center", minHeight: 48, gap: spacing.md, borderBottomWidth: i === h.students!.length - 1 ? 0 : 1, borderBottomColor: colors.divider }}
                    >
                      <Txt variant="body" raw numberOfLines={1} style={{ flex: 1 }}>{s.roll_no ? `${s.roll_no}. ` : ""}{s.name}</Txt>
                      <View style={{ paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: tone[0] }}>
                        <Txt variant="caption" raw color={tone[1]}>{m ? LABEL[m] : "—"}</Txt>
                      </View>
                    </Pressable>
                  );
                })}
              </Card>
            </View>
          ) : null}
        </ScrollView>
      ) : null}
      {h ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          {h.status === "draft" ? (
            <Button testID="hw-publish-button" title="Publish to parents" loading={publish.isPending} onPress={() => publish.mutate()} />
          ) : (
            <Button testID="hw-save-completion" title="Save completion" disabled={!dirty} loading={saveComp.isPending} onPress={() => saveComp.mutate()} />
          )}
        </View>
      ) : null}
      <Sheet visible={confirm} onClose={() => setConfirm(false)} title="Delete homework?" testID="hw-delete-sheet" footer={<Button testID="hw-delete-confirm" variant="danger" title="Delete" loading={del.isPending} onPress={() => del.mutate()} />}>
        <Txt variant="body">Parents will no longer see this homework. This is recorded in the audit log.</Txt>
      </Sheet>
    </View>
  );
}
