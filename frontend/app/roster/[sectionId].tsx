import { useInfiniteQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { UsersThree } from "phosphor-react-native";
import React from "react";
import { ActivityIndicator, FlatList, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { EmptyState, ErrorState, Header, Row, SkeletonList, Txt } from "@/src/components/ui";
import { initials } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";
import type { Student } from "@/src/types";

export default function Roster() {
  const { sectionId } = useLocalSearchParams<{ sectionId: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const q = useInfiniteQuery({
    queryKey: ["roster", membership?.school_id, sectionId],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => api<Paged<Student>>(`/students?section_id=${sectionId}&page=${pageParam}&page_size=30`),
    getNextPageParam: (l) => (l.has_more ? l.page + 1 : undefined),
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const first = items[0];
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={first ? `${first.class_name} - ${first.section_name}` : "Roster"} subtitle={q.data ? `${q.data.pages[0].total} students` : undefined} />
      {q.isLoading ? (
        <SkeletonList />
      ) : q.isError ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
      ) : (
        <FlatList
          testID="roster-list"
          data={items}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}
          onEndReached={() => q.hasNextPage && !q.isFetchingNextPage && q.fetchNextPage()}
          ListEmptyComponent={<EmptyState icon={<UsersThree size={40} color={colors.muted} />} title="No students in this section" />}
          ListFooterComponent={q.isFetchingNextPage ? <ActivityIndicator style={{ margin: spacing.lg }} /> : null}
          renderItem={({ item, index }) => (
            <Row
              testID={`roster-row-${item.admission_no}`}
              last={index === items.length - 1}
              icon={
                <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="label" color={colors.onBrandTertiary}>{initials(`${item.first_name} ${item.last_name}`)}</Txt>
                </View>
              }
              title={`${item.roll_no ? `${item.roll_no}. ` : ""}${item.first_name} ${item.last_name}`}
              subtitle={`Adm. ${item.admission_no} · ${item.gender}`}
            />
          )}
        />
      )}
    </View>
  );
}
