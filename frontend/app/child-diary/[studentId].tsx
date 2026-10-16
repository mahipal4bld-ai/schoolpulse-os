import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { BookOpenText } from "phosphor-react-native";
import React, { useState } from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { DayStepper, DiaryEntry, DiaryItem } from "@/src/components/diary";
import { isoDay } from "@/src/components/homework";
import { Card, EmptyState, ErrorState, Header, SkeletonList } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function ChildDiary() {
  const { studentId, name } = useLocalSearchParams<{ studentId: string; name?: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [day, setDay] = useState(isoDay());
  const q = useQuery({
    queryKey: ["parent-diary", membership?.school_id, studentId, day],
    queryFn: () => api<{ date: string; items: DiaryEntry[] }>(`/parent/children/${studentId}/diary?date=${day}`),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Class diary" subtitle={name} />
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <DayStepper value={day} onChange={setDay} />
      </View>
      {q.isLoading ? <SkeletonList rows={3} /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}>
          {q.data!.items.length ? (
            <Card style={{ paddingVertical: spacing.xs }} testID="parent-diary-list">
              {q.data!.items.map((e) => <DiaryItem key={e.id} e={e} />)}
            </Card>
          ) : (
            <EmptyState icon={<BookOpenText size={40} color={colors.muted} />} title="No diary for this day" message="Teachers' daily class updates appear here." />
          )}
        </ScrollView>
      )}
    </View>
  );
}
