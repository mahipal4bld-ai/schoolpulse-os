import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ChartBar, CheckCircle, PencilSimpleLine } from "phosphor-react-native";
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ExamT, STATUS_LABEL } from "@/src/components/exams";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Header, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function ExamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["exam", membership?.school_id, id];
  const q = useQuery({ queryKey: key, queryFn: () => api<ExamT>(`/exams/${id}`) });
  const status = useMutation({
    mutationFn: (s: "published" | "marks_open") => api<ExamT>(`/exams/${id}/status?status=${s}`, { method: "POST" }),
    onSuccess: (d) => {
      qc.setQueryData(key, d);
      qc.invalidateQueries({ queryKey: ["exams"] });
      toast.show(d.status === "published" ? "Results published to parents" : "Marks entry re-opened");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const e = q.data;
  const manage = can("academic.manage");
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={e?.name ?? "Exam"} subtitle={e ? `${formatDate(e.start_date)} – ${formatDate(e.end_date)}` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : e ? (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
          <Card style={{ gap: spacing.sm }} testID="exam-summary-card">
            <Badge testID="exam-status-badge" tone={e.status === "published" ? "success" : "warning"} label={STATUS_LABEL[e.status]} />
            <Txt variant="label" raw testID="exam-progress">Marks entered {e.progress.entered}/{e.progress.total}</Txt>
            <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" }}>
              <View style={{ height: 8, width: `${e.progress.total ? (100 * e.progress.entered) / e.progress.total : 0}%`, backgroundColor: colors.brandSecondary }} />
            </View>
            <Txt variant="caption" raw>{e.subjects.map((s) => `${s.subject_name} (${s.max_marks})`).join(" · ")}</Txt>
          </Card>
          <View>
            <SectionTitle title="Marks entry" />
            <Card style={{ paddingVertical: 0 }}>
              {e.sheets.map((s, i) => (
                <Row key={`${s.section_id}-${s.subject_id}`} testID={`exam-sheet-${s.section_id}-${s.subject_id}`} last={i === e.sheets.length - 1}
                  icon={<IconTile>{s.entered ? <CheckCircle size={18} color={colors.onBrandTertiary} /> : <PencilSimpleLine size={18} color={colors.onBrandTertiary} />}</IconTile>}
                  title={`${s.section_label} · ${s.subject_name}`} subtitle={s.entered ? "Entered" : "Pending"}
                  onPress={() => router.push({ pathname: "/exams/marks", params: { exam: id, section: s.section_id, subject: s.subject_id } })} />
              ))}
            </Card>
          </View>
          <View>
            <SectionTitle title="Results" />
            <Card style={{ paddingVertical: 0 }}>
              {e.sections.map((s, i) => (
                <Row key={s.id} testID={`exam-results-${s.id}`} last={i === e.sections.length - 1} icon={<IconTile><ChartBar size={18} color={colors.onBrandTertiary} /></IconTile>} title={s.label} subtitle="Ranks, grades and report cards" onPress={() => router.push({ pathname: "/exams/results", params: { exam: id, section: s.id } })} />
              ))}
            </Card>
          </View>
        </ScrollView>
      ) : null}
      {e && manage ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          {e.status === "marks_open" ? (
            <Button testID="exam-publish-button" title="Publish results" loading={status.isPending} onPress={() => status.mutate("published")} />
          ) : (
            <Button testID="exam-reopen-button" variant="outline" title="Re-open marks entry" loading={status.isPending} onPress={() => status.mutate("marks_open")} />
          )}
        </View>
      ) : null}
    </View>
  );
}
