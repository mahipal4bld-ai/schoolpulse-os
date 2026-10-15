import { useInfiniteQuery } from "@tanstack/react-query";
import { ClockCounterClockwise } from "phosphor-react-native";
import React from "react";
import { FlatList, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { EmptyState, ErrorState, Header, Row, SkeletonList } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function Audit() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useInfiniteQuery({
    queryKey: ["audit", membership?.school_id],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => api<Paged<any>>(`/audit-logs?page=${pageParam}`),
    getNextPageParam: (l) => (l.page * l.page_size < l.total ? l.page + 1 : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Audit log" subtitle={q.data ? `${q.data.pages[0].total} events` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="audit-list"
          data={items}
          keyExtractor={(i) => i.id}
          onEndReached={() => q.hasNextPage && !q.isFetchingNextPage && q.fetchNextPage()}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<ClockCounterClockwise size={40} color={colors.muted} />} title="No activity yet" />}
          renderItem={({ item, index }) => (
            <Row last={index === items.length - 1} title={item.action.replace(/[._]/g, " ")} subtitle={`${item.actor_name ?? "System"} · ${formatDateTime(item.at)}`} />
          )}
        />
      )}
    </View>
  );
}
