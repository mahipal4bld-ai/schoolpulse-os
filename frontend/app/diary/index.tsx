import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { BookOpenText } from "phosphor-react-native";
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Card, EmptyState, ErrorState, Header, IconTile, Row, SkeletonList } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type Opt = { section_id: string; label: string };

export default function DiarySections() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const q = useQuery({ queryKey: ["homework-options"], queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Class diary" subtitle="Choose a section" />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : !q.data!.items.length ? (
        <EmptyState title="No classes assigned" message="You can write the diary once a section is assigned to you." />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
          <Card style={{ paddingVertical: 0 }}>
            {q.data!.items.map((o, i) => (
              <Row key={o.section_id} testID={`diary-section-${o.section_id}`} last={i === q.data!.items.length - 1} icon={<IconTile><BookOpenText size={18} color={colors.onBrandTertiary} /></IconTile>} title={o.label} onPress={() => router.push(`/diary/${o.section_id}`)} />
            ))}
          </Card>
        </ScrollView>
      )}
    </View>
  );
}
