import { useRouter } from "expo-router";
import { Chalkboard } from "phosphor-react-native";
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTeacherDash } from "@/src/teacher-dash";
import { Badge, Card, EmptyState, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { spacing, useTheme } from "@/src/theme";

export default function TeacherClasses() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const q = useTeacherDash();
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header title={t("classes")} subtitle="Tap a section to open its roster" />
      {q.isLoading ? (
        <SkeletonList />
      ) : q.isError ? (
        <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
      ) : !q.data?.sections.length ? (
        <EmptyState icon={<Chalkboard size={40} color={colors.muted} />} title="No classes assigned yet" />
      ) : (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.md }}>
          {q.data.sections.map((s) => (
            <Card key={s.section_id} testID={`class-card-${s.section_id}`} style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <Txt variant="heading">{s.label}</Txt>
                {s.is_class_teacher ? <Badge label={t("classTeacher")} tone="brand" /> : null}
              </View>
              <Txt variant="caption">{s.subjects.join(" · ") || "General"} · {s.students} students</Txt>
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                <Badge label="Attendance · coming soon" />
                <Badge label="Homework · coming soon" />
              </View>
              <Txt variant="label" color={colors.brandPrimary} testID={`open-roster-${s.section_id}`} onPress={() => router.push(`/roster/${s.section_id}`)} style={{ marginTop: spacing.sm, minHeight: 32 }}>
                Open roster →
              </Txt>
            </Card>
          ))}
        </ScrollView>
      )}
    </View>
  );
}
