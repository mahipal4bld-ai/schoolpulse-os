import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { Exam } from "phosphor-react-native";
import React from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ReportCardButton, SubjectLine, SubjectLines } from "@/src/components/exams";
import { Badge, Card, EmptyState, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type R = { id: string; name: string; term: string; percentage: number | null; grade: string | null; result: string | null; rank: number | null; class_size: number; total: number; max_total: number; subjects: SubjectLine[] };

export default function ChildExams() {
  const { studentId, name } = useLocalSearchParams<{ studentId: string; name?: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useQuery({ queryKey: ["parent-exams", membership?.school_id, studentId], queryFn: () => api<{ items: R[] }>(`/parent/children/${studentId}/exams`) });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Exam results" subtitle={name} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="parent-exams-list"
          data={q.data!.items}
          keyExtractor={(e) => e.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<Exam size={40} color={colors.muted} />} title="No results yet" message="Results appear here once the school publishes them." />}
          renderItem={({ item }) => (
            <Card testID={`parent-exam-${item.id}`} style={{ gap: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Txt variant="label" raw>{item.name}</Txt>
                  {item.term ? <Txt variant="caption" raw>{item.term}</Txt> : null}
                </View>
                {item.result ? <Badge tone={item.result === "Pass" ? "success" : "error"} label={item.result} /> : null}
              </View>
              <View style={{ flexDirection: "row", gap: spacing.lg }}>
                <View><Txt variant="heading" raw testID={`parent-exam-pct-${item.id}`}>{item.percentage ?? "—"}%</Txt><Txt variant="caption">Percentage</Txt></View>
                <View><Txt variant="heading" raw>{item.grade ?? "—"}</Txt><Txt variant="caption">Grade</Txt></View>
                <View><Txt variant="heading" raw>{item.rank ?? "—"}/{item.class_size}</Txt><Txt variant="caption">Rank</Txt></View>
              </View>
              <SubjectLines lines={item.subjects} />
              <ReportCardButton examId={item.id} studentId={studentId} testID={`parent-report-card-${item.id}`} />
            </Card>
          )}
        />
      )}
    </View>
  );
}
