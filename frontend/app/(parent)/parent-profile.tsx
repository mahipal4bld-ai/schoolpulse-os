import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AccountPanel } from "@/src/components/account-panel";
import { Header } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { spacing, useTheme } from "@/src/theme";

export default function ParentProfile() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header title={t("profile")} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl }}>
        <AccountPanel />
      </ScrollView>
    </View>
  );
}
