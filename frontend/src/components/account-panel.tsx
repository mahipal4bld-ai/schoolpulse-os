import { Buildings, GlobeHemisphereEast, SignOut, UserCircle } from "phosphor-react-native";
import { useRouter } from "expo-router";
import React from "react";
import { View } from "react-native";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Card, IconTile, Row, Segmented, SectionTitle, Txt } from "@/src/components/ui";
import { ROLE_LABEL } from "@/src/format";
import { setLang, useI18n } from "@/src/i18n";
import { spacing, useTheme } from "@/src/theme";

export function AccountPanel() {
  const { me, membership, logout } = useAuth();
  const { t, lang } = useI18n();
  const { colors } = useTheme();
  const router = useRouter();
  if (!me) return null;
  return (
    <View style={{ gap: spacing.xl }}>
      <Card testID="account-card">
        <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "center" }}>
          <IconTile>
            <UserCircle size={22} color={colors.onBrandTertiary} />
          </IconTile>
          <View style={{ flex: 1, gap: 2 }}>
            <Txt variant="label">{me.user.name}</Txt>
            <Txt variant="caption">{me.user.email}</Txt>
          </View>
          {membership ? <Badge tone="brand" label={ROLE_LABEL[membership.role]} testID="account-role-badge" /> : null}
        </View>
      </Card>

      <View>
        <SectionTitle title={t("language")} />
        <Segmented
          testIDPrefix="language-toggle"
          value={lang}
          onChange={(v) => {
            setLang(v);
            api("/auth/me/preferences", { method: "PATCH", body: { preferred_language: v }, noSchool: true }).catch(() => {});
          }}
          options={[
            { value: "en", label: "English" },
            { value: "hi", label: "हिंदी" },
          ]}
        />
      </View>

      <Card style={{ paddingVertical: 0 }}>
        {me.memberships.length > 1 ? (
          <Row
            testID="switch-school-row"
            icon={
              <IconTile>
                <Buildings size={18} color={colors.onBrandTertiary} />
              </IconTile>
            }
            title={t("switchSchool")}
            subtitle={`${me.memberships.length} schools linked to this account`}
            onPress={() => router.push("/select-school")}
          />
        ) : null}
        <Row
          testID="sign-out-all-row"
          icon={
            <IconTile tone={colors.errorSoft}>
              <SignOut size={18} color={colors.error} />
            </IconTile>
          }
          title="Sign out of all devices"
          subtitle="Revokes every active session for this account"
          onPress={async () => {
            await api("/auth/logout-all", { method: "POST", noSchool: true }).catch(() => {});
            await logout();
            router.replace("/login");
          }}
        />
        <Row
          testID="sign-out-row"
          last
          icon={
            <IconTile tone={colors.errorSoft}>
              <SignOut size={18} color={colors.error} />
            </IconTile>
          }
          title={t("signOut")}
          subtitle="Ends this session on the server"
          onPress={async () => {
            await logout();
            router.replace("/login");
          }}
        />
      </Card>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, justifyContent: "center" }}>
        <GlobeHemisphereEast size={14} color={colors.muted} />
        <Txt variant="caption">SchoolPulse OS · Milestone 1 · Times shown in IST</Txt>
      </View>
    </View>
  );
}
