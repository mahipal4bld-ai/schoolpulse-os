import { BellSimple } from "phosphor-react-native";
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Card, EmptyState, Header } from "@/src/components/ui";
import { UpcomingModules } from "@/src/components/upcoming-modules";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { spacing, useTheme } from "@/src/theme";

export default function ParentUpdates() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header title={t("updates")} subtitle="Notices, homework and messages" />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}>
        <Card>
          <EmptyState testID="updates-empty-state" icon={<BellSimple size={36} color={colors.muted} />} title="No updates yet" message="School notices, homework and class diary entries will appear here once these modules launch." />
        </Card>
        <View>
          <UpcomingModules role="parent" />
        </View>
      </ScrollView>
    </View>
  );
}
