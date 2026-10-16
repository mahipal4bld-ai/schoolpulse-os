import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { NotePencil } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { AttachmentList, Homework } from "@/src/components/homework";
import { Badge, Card, EmptyState, ErrorState, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

const MY = { done: ["Completed", "success"], late: ["Submitted late", "warning"], not_done: ["Not done", "error"] } as const;

export default function ChildHomework() {
  const { studentId, name } = useLocalSearchParams<{ studentId: string; name?: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [scope, setScope] = useState<"upcoming" | "past">("upcoming");
  const q = useQuery({
    queryKey: ["parent-hw", membership?.school_id, studentId, scope],
    queryFn: () => api<{ items: Homework[] }>(`/parent/children/${studentId}/homework?scope=${scope}`),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Homework" subtitle={name} />
      <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md }}>
        <Segmented testIDPrefix="parent-hw-scope" value={scope} onChange={setScope} options={[{ value: "upcoming", label: "Upcoming" }, { value: "past", label: "Past" }]} />
      </View>
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="parent-homework-list"
          data={q.data!.items}
          keyExtractor={(h) => h.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<NotePencil size={40} color={colors.muted} />} title={scope === "upcoming" ? "No homework due" : "No past homework"} message="Homework published by teachers appears here." />}
          renderItem={({ item }) => (
            <Card testID={`parent-hw-${item.id}`} style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <Txt variant="label" raw style={{ flex: 1 }}>{item.subject_name}</Txt>
                <Badge tone="brand" label={`Due ${formatDate(item.due_date)}`} />
              </View>
              <Txt variant="body" raw style={{ fontWeight: "600" }}>{item.title}</Txt>
              {item.description ? <Txt variant="body" raw>{item.description}</Txt> : null}
              <AttachmentList items={item.attachments} testIDPrefix="parent-hw-file" />
              {item.my_status ? <Badge testID={`parent-hw-status-${item.id}`} tone={MY[item.my_status][1]} label={MY[item.my_status][0]} /> : null}
            </Card>
          )}
        />
      )}
    </View>
  );
}
