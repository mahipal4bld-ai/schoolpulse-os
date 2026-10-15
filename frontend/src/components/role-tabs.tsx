import { Redirect, Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import * as Haptics from "expo-haptics";
import React from "react";
import { Platform } from "react-native";

import { homeRoute, useAuth } from "@/src/auth";
import { LoadingState } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, useTheme } from "@/src/theme";
import type { Role } from "@/src/types";

export type TabDef = {
  name: string;
  label: string;
  sf: string;
  icon: (p: { color: string; size: number; focused: boolean }) => React.ReactNode;
};

export function RoleTabs({ tabs, allow }: { tabs: TabDef[]; allow: (role: Role) => boolean }) {
  const { status, me, membership } = useAuth();
  const { colors } = useTheme();
  if (status === "loading") return <LoadingState />;
  if (status === "signedOut") return <Redirect href="/login" />;
  if (!membership || !allow(membership.role)) return <Redirect href={homeRoute(me, membership) as any} />;

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        {tabs.map((t) => (
          <NativeTabs.Trigger key={t.name} name={t.name}>
            <NativeTabs.Trigger.Icon sf={t.sf as any} />
            <NativeTabs.Trigger.Label>{t.label}</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
        ))}
      </NativeTabs>
    );
  }
  return (
    <Tabs
      screenListeners={{ tabPress: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}) }}
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 11 },
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
      }}
    >
      {tabs.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.label,
            tabBarButtonTestID: `tab-${t.name}`,
            tabBarIcon: ({ color, size, focused }) => t.icon({ color: color as string, size: size - 2, focused }),
          }}
        />
      ))}
    </Tabs>
  );
}
