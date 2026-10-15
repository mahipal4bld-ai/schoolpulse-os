import { useRouter } from "expo-router";
import { ShieldCheck } from "phosphor-react-native";
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { homeRoute, useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { Badge, Button, Card, IconTile, Row, Txt } from "@/src/components/ui";
import { ROLE_LABEL } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function SelectSchool() {
  const { me, selectSchool, logout } = useAuth();
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const router = useRouter();
  if (!me) return null;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + spacing.xxl, paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
        <View style={{ gap: spacing.sm, paddingHorizontal: spacing.sm }}>
          <Txt variant="title">Choose a school</Txt>
          <Txt variant="body" color={colors.muted}>
            Your account is linked to {me.memberships.length} schools. Each school&apos;s data stays separate.
          </Txt>
        </View>
        <Card style={{ paddingVertical: 0 }}>
          {me.memberships.map((m, i) => (
            <Row
              key={m.school_id}
              testID={`select-school-${m.school.slug}`}
              last={i === me.memberships.length - 1 && me.user.platform_role !== "super_admin"}
              icon={<SchoolLogo brand={m.school.brand} size={40} />}
              title={m.school.name}
              subtitle={ROLE_LABEL[m.role]}
              onPress={async () => {
                await selectSchool(m.school_id);
                router.replace(homeRoute(me, m) as any);
              }}
            />
          ))}
          {me.user.platform_role === "super_admin" ? (
            <Row
              testID="select-platform-admin"
              last
              icon={
                <IconTile>
                  <ShieldCheck size={18} color={colors.onBrandTertiary} />
                </IconTile>
              }
              title="SchoolPulse platform"
              subtitle="Super admin console"
              right={<Badge label="Platform" tone="brand" />}
              onPress={async () => {
                await selectSchool(null);
                router.replace("/platform");
              }}
            />
          ) : null}
        </Card>
        <Button
          testID="select-school-sign-out"
          variant="ghost"
          title="Sign out"
          onPress={async () => {
            await logout();
            router.replace("/login");
          }}
        />
      </ScrollView>
    </View>
  );
}
