import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { FlatList, Pressable, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { ReportCardButton, SubjectLine, SubjectLines } from "@/src/components/exams";
import { Badge, Card, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type Row = { student_id: string; name: string; roll_no?: number; total: number; max_total: number; percentage: number | null; grade: string | null; result: string | null; rank: number | null; subjects: SubjectLine[] };
type Res = { exam: string; status: string; section: string; rows: Row[]; class_average: number | null; pass_count: number; students: number };

export default function ExamResults() {
  const { exam, section } = useLocalSearchParams<{ exam: string; section: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["exam-results", exam, section], queryFn: () => api<Res>(`/exams/${exam}/results?section_id=${section}`) });
  const rows = [...(q.data?.rows ?? [])].sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Results" subtitle={q.data ? `${q.data.exam} · ${q.data.section}` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="results-list"
          data={rows}
          keyExtractor={(r) => r.student_id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.sm }}
          ListHeaderComponent={
            <Card style={{ flexDirection: "row", gap: spacing.lg, marginBottom: spacing.sm }} testID="results-summary">
              <View><Txt variant="heading" raw>{q.data!.class_average ?? "—"}%</Txt><Txt variant="caption">Class average</Txt></View>
              <View><Txt variant="heading" raw>{q.data!.pass_count}/{q.data!.students}</Txt><Txt variant="caption">Passed</Txt></View>
            </Card>
          }
          renderItem={({ item }) => (
            <Pressable testID={`result-row-${item.student_id}`} onPress={() => setOpenId(openId === item.student_id ? null : item.student_id)}>
              <Card style={{ gap: spacing.sm }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Txt variant="label" raw style={{ width: 32 }}>{item.rank ? `#${item.rank}` : "—"}</Txt>
                  <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{item.name}</Txt>
                  <Txt variant="label" raw>{item.percentage ?? "—"}%</Txt>
                  {item.result ? <Badge tone={item.result === "Pass" ? "success" : "error"} label={`${item.grade ?? ""} ${item.result}`} /> : null}
                </View>
                {openId === item.student_id ? (
                  <>
                    <SubjectLines lines={item.subjects} />
                    <ReportCardButton examId={exam} studentId={item.student_id} testID={`report-card-${item.student_id}`} />
                  </>
                ) : null}
              </Card>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}
