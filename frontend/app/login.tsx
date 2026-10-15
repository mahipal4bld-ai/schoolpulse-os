import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ArrowRight, EnvelopeSimple, GraduationCap, Key, ShieldCheck, Student, UserGear, Users } from "phosphor-react-native";
import React, { useState } from "react";
import { Pressable, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { homeRoute, useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, Field, IconTile, Row, Txt } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { fonts, radius, spacing, useTheme } from "@/src/theme";

type Demo = { password: string; accounts: { email: string; name: string; label: string }[] };

function demoIcon(email: string, color: string) {
  if (email.startsWith("superadmin")) return <ShieldCheck size={18} color={color} />;
  if (email.startsWith("owner")) return <UserGear size={18} color={color} />;
  if (email.startsWith("teacher")) return <GraduationCap size={18} color={color} />;
  if (email.includes("parent")) return <Users size={18} color={color} />;
  return <Student size={18} color={color} />;
}

export default function Login() {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { t } = useI18n();
  const { login, acceptInvite } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [invite, setInvite] = useState({ token: "", name: "", password: "" });

  // Developer-only: endpoint returns 404 unless backend DEMO_MODE=true.
  const demo = useQuery({ queryKey: ["demo-accounts"], queryFn: () => api<Demo>("/auth/demo-accounts", { noSchool: true }), retry: false });

  const go = async (e: string, p: string) => {
    setError("");
    if (!e.trim() || !p) return setError("Enter your email and password");
    setBusy(true);
    try {
      const me = await login(e.trim(), p);
      const only = me.memberships.length === 1 ? me.memberships[0] : null;
      router.replace(homeRoute(me, only) as any);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ flexGrow: 1, width: "100%", maxWidth: 520, alignSelf: "center", paddingTop: insets.top + spacing.xxxl, paddingBottom: insets.bottom + spacing.xl, paddingHorizontal: spacing.xl }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <View style={{ width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}>
            <View style={{ width: 14, height: 14, borderRadius: 7, borderWidth: 3, borderColor: colors.brandSecondary }} />
          </View>
          <View>
            <Txt variant="heading">SchoolPulse OS</Txt>
            <Txt variant="caption">School operating system</Txt>
          </View>
        </View>

        <View style={{ marginTop: spacing.xxxl, gap: spacing.sm }}>
          <Txt variant="display">{t("welcomeBack")}</Txt>
          <Txt variant="body" color={colors.muted}>
            {t("signInSubtitle")}
          </Txt>
        </View>

        <View style={{ marginTop: spacing.xxl, gap: spacing.lg }}>
          <Field testID="login-email-input" label={t("email")} value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" placeholder="you@school.in" />
          <Field testID="login-password-input" label={t("password")} value={password} onChangeText={setPassword} secureTextEntry placeholder="••••••••" onSubmitEditing={() => go(email, password)} />
          {error ? (
            <Txt testID="login-error-text" variant="caption" color={colors.error}>
              {error}
            </Txt>
          ) : null}
          <Button testID="login-submit-button" title={t("signIn")} loading={busy} onPress={() => go(email, password)} icon={!busy ? undefined : null} />
          <Pressable testID="open-invite-button" onPress={() => setInviteOpen(true)} style={{ minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm }}>
            <Key size={16} color={colors.brandPrimary} />
            <Txt variant="label" color={colors.brandPrimary}>
              {t("haveInvite")}
            </Txt>
          </Pressable>
        </View>

        <View style={{ flex: 1 }} />
        {demo.data ? (
          <Pressable
            testID="open-demo-picker-button"
            onPress={() => setDemoOpen(true)}
            style={({ pressed }) => ({
              marginTop: spacing.xxl,
              borderRadius: radius.lg,
              borderWidth: 1,
              borderStyle: "dashed",
              borderColor: colors.borderStrong,
              padding: spacing.lg,
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.md,
              backgroundColor: pressed ? colors.surfaceSecondary : colors.surface,
            })}
          >
            <IconTile>
              <Users size={18} color={colors.onBrandTertiary} />
            </IconTile>
            <View style={{ flex: 1 }}>
              <Txt variant="label">{t("useDemo")}</Txt>
              <Txt variant="caption">Developer preview only · fictional data</Txt>
            </View>
            <ArrowRight size={18} color={colors.muted} />
          </Pressable>
        ) : null}
      </KeyboardAwareScrollView>

      <Sheet visible={demoOpen} onClose={() => setDemoOpen(false)} title="Demo accounts" testID="demo-picker-sheet">
        <Txt variant="caption">
          Signs in with the normal password flow. Password for all demo accounts:{" "}
          <Txt variant="caption" style={{ fontFamily: fonts.medium }} color={colors.onSurface}>
            {demo.data?.password}
          </Txt>
        </Txt>
        <View>
          {demo.data?.accounts.map((a, i) => (
            <Row
              key={a.email}
              testID={`demo-account-${a.email}`}
              last={i === (demo.data?.accounts.length ?? 0) - 1}
              icon={<IconTile>{demoIcon(a.email, colors.onBrandTertiary)}</IconTile>}
              title={a.label}
              subtitle={a.email}
              onPress={() => {
                setDemoOpen(false);
                setEmail(a.email);
                setPassword(demo.data!.password);
                go(a.email, demo.data!.password);
              }}
            />
          ))}
        </View>
      </Sheet>

      <Sheet
        visible={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title="Accept invitation"
        testID="accept-invite-sheet"
        footer={
          <Button
            testID="accept-invite-submit-button"
            title="Join school"
            loading={busy}
            onPress={async () => {
              setBusy(true);
              try {
                const me = await acceptInvite(invite.token.trim(), invite.name.trim(), invite.password);
                setInviteOpen(false);
                toast.show("Invitation accepted. Welcome aboard!");
                router.replace(homeRoute(me, me.memberships.length === 1 ? me.memberships[0] : null) as any);
              } catch (e: any) {
                toast.show(e.message, "error");
              } finally {
                setBusy(false);
              }
            }}
          />
        }
      >
        <Txt variant="caption">Enter the invitation code shared by your school administrator.</Txt>
        <Field testID="invite-code-input" label="Invitation code" value={invite.token} onChangeText={(v) => setInvite({ ...invite, token: v })} autoCapitalize="none" />
        <Field testID="invite-name-input" label="Full name" value={invite.name} onChangeText={(v) => setInvite({ ...invite, name: v })} />
        <Field testID="invite-password-input" label="Create password" hint="At least 8 characters" value={invite.password} secureTextEntry onChangeText={(v) => setInvite({ ...invite, password: v })} />
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
          <EnvelopeSimple size={14} color={colors.muted} />
          <Txt variant="caption">Invitations expire after 14 days.</Txt>
        </View>
      </Sheet>
    </View>
  );
}
