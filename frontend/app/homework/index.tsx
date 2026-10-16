import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { NotePencil, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Homework } from "@/src/components/homework";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Filter = "all" | "published" | "draft";

export default function HomeworkList() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>("all");
  const scope = can("academic.manage") ? "all" : "mine";
  const q = useQuery({
    queryKey: ["homework", membership?.school_id, filter],
    queryFn: () => api<{ items: Homework[] }>(`/homework?scope=${scope}${filter === "all" ? "" : `&status=${filter}`}`),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Homework" subtitle={scope === "all" ? "All sections" : "Assigned by you"} />
      <ChipRow testIDPrefix="homework-filter" value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "published", label: "Published" }, { value: "draft", label: "Drafts" }]} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="homework-list"
          data={q.data!.items}
          keyExtractor={(h) => h.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<NotePencil size={40} color={colors.muted} />} title="No homework yet" message={scope === "all" ? "No homework has been created in any section yet." : "Create homework for your classes. Parents see it once published."} />}
          renderItem={({ item }) => (
            <Card testID={`homework-card-${item.id}`} style={{ gap: spacing.xs }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                <Txt variant="caption" raw style={{ flex: 1 }}>{item.section_label} · {item.subject_name}</Txt>
                <Badge tone={item.status === "published" ? "success" : "neutral"} label={item.status} />
              </View>
              <Txt variant="label" raw numberOfLines={2}>{item.title}</Txt>
              <Txt variant="caption" raw>Due {formatDate(item.due_date)}{item.attachments.length ? ` · ${item.attachments.length} file(s)` : ""}{item.completion_counts && item.status === "published" ? ` · ${item.completion_counts.done} done` : ""}</Txt>
              <Button small variant="outline" title="Open" testID={`homework-open-${item.id}`} onPress={() => router.push(`/homework/${item.id}`)} style={{ marginTop: spacing.xs }} />
            </Card>
          )}
        />
      )}
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Button testID="new-homework-button" title="New homework" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => router.push("/homework/new")} />
      </View>
    </View>
  );
}
