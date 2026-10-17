import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFocusEffect } from "expo-router";
import { Megaphone } from "phosphor-react-native";
import React, { useCallback } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Notice, NoticeCard } from "@/src/components/notices";
import { useToast } from "@/src/components/toast";
import { Badge, Button, EmptyState, ErrorState, Header, SkeletonList } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function ParentNotices() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["parent-notices", membership?.school_id];
  const q = useQuery({ queryKey: key, queryFn: () => api<{ items: Notice[]; unread: number }>("/parent/notices") });
  const read = useMutation({ mutationFn: (id: string) => api(`/parent/notices/${id}/read`, { method: "POST" }) });
  const ack = useMutation({
    mutationFn: (id: string) => api(`/parent/notices/${id}/ack`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); toast.show("Acknowledged. Thank you."); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  // Opening the list marks visible notices as read (a read receipt — never an acknowledgement).
  const { data } = q;
  useFocusEffect(useCallback(() => {
    const unread = data?.items.filter((n) => !n.read) ?? [];
    if (unread.length) Promise.all(unread.map((n) => read.mutateAsync(n.id))).then(() => qc.invalidateQueries({ queryKey: ["parent-notices-count"] })).catch(() => {});
  }, [data]));  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="School notices" subtitle={q.data?.unread ? `${q.data.unread} new` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="parent-notices-list"
          data={q.data!.items}
          keyExtractor={(n) => n.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<Megaphone size={40} color={colors.muted} />} title="No notices" message="Announcements from school appear here." />}
          renderItem={({ item }) => (
            <NoticeCard n={item} footer={item.requires_ack ? (item.acknowledged ? <Badge testID={`notice-acked-${item.id}`} tone="success" label="Acknowledged" /> : <Button small testID={`notice-ack-${item.id}`} title="Acknowledge" loading={ack.isPending && ack.variables === item.id} onPress={() => ack.mutate(item.id)} />) : null} />
          )}
        />
      )}
    </View>
  );
}
