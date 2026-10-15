import { useRouter } from "expo-router";
import { Buildings, ClockCounterClockwise, EnvelopeSimple, FileCsv, PaintBrush } from "phosphor-react-native";
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "@/src/auth";
import { AccountPanel } from "@/src/components/account-panel";
import { Card, Header, IconTile, Row, SectionTitle } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { spacing, useTheme } from "@/src/theme";

export default function Settings() {
  const { can, membership } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const ic = colors.onBrandTertiary;
  const rows = [
    can("brand.manage") && { id: "brand-studio", title: t("brandStudio"), sub: "Logo, colours, banner and welcome message", icon: <PaintBrush size={18} color={ic} />, href: "/brand-studio" },
    { id: "school-profile", title: t("schoolProfile"), sub: can("school.manage") ? "Contact, session, timings and language" : "View school information", icon: <Buildings size={18} color={ic} />, href: "/school-profile" },
    can("staff.manage") && { id: "invitations", title: t("invitations"), sub: "Invite principals, teachers and staff", icon: <EnvelopeSimple size={18} color={ic} />, href: "/invitations" },
    can("people.manage") && { id: "import", title: t("importCsv"), sub: "Validate and import admissions in bulk", icon: <FileCsv size={18} color={ic} />, href: "/import" },
    can("audit.view") && { id: "audit", title: t("auditLog"), sub: "Every change, who made it and when", icon: <ClockCounterClockwise size={18} color={ic} />, href: "/audit" },
  ].filter(Boolean) as { id: string; title: string; sub: string; icon: React.ReactNode; href: string }[];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header title={t("settings")} subtitle={membership?.school.name} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}>
        <View>
          <SectionTitle title="School" />
          <Card style={{ paddingVertical: 0 }}>
            {rows.map((r, i) => (
              <Row key={r.id} testID={`settings-${r.id}`} last={i === rows.length - 1} icon={<IconTile>{r.icon}</IconTile>} title={r.title} subtitle={r.sub} onPress={() => router.push(r.href as any)} />
            ))}
          </Card>
        </View>
        <AccountPanel />
      </ScrollView>
    </View>
  );
}
