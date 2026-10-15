import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Buildings, MagnifyingGlass, Plus, ShieldCheck } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, EmptyState, ErrorState, Field, IconTile, SkeletonList, Txt } from "@/src/components/ui";
import { fonts, radius, spacing, type, useTheme } from "@/src/theme";
import type { School } from "@/src/types";

type Tenant = School & { student_quota: number; usage: { students: number; teachers: number; members: number } };

export default function Platform() {
  const { me, logout } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", slug: "", city: "", owner_name: "", owner_email: "", owner_password: "" });
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const stats = useQuery({ queryKey: ["platform-stats"], queryFn: () => api("/platform/stats", { noSchool: true }) });
  const list = useQuery({ queryKey: ["platform-schools", search], queryFn: () => api<{ items: Tenant[] }>(`/platform/schools?q=${encodeURIComponent(search)}`, { noSchool: true }) });

  const create = useMutation({
    mutationFn: () => api("/platform/schools", { noSchool: true, body: { ...f, plan: "trial" } }),
    onSuccess: () => {
      setOpen(false);
      setF({ name: "", slug: "", city: "", owner_name: "", owner_email: "", owner_password: "" });
      qc.invalidateQueries({ queryKey: ["platform-schools"] });
      qc.invalidateQueries({ queryKey: ["platform-stats"] });
      toast.show("School created with its owner account");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const toggle = useMutation({
    mutationFn: (s: Tenant) => api(`/platform/schools/${s.id}`, { method: "PATCH", noSchool: true, body: { status: s.status === "suspended" ? "active" : "suspended" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-schools"] }),
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  if (me?.user.platform_role !== "super_admin") return <EmptyState title="Platform access required" />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.md }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
          <IconTile><ShieldCheck size={20} color={colors.onBrandTertiary} /></IconTile>
          <View style={{ flex: 1 }}>
            <Txt variant="heading">SchoolPulse Console</Txt>
            <Txt variant="caption">Super admin · tenant management</Txt>
          </View>
          <Button small variant="outline" testID="platform-sign-out" title="Sign out" onPress={async () => { await logout(); router.replace("/login"); }} />
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {[["Schools", stats.data?.schools], ["Active", stats.data?.active_schools], ["Students", stats.data?.students], ["Users", stats.data?.users]].map(([k, v]) => (
            <View key={k as string} testID={`platform-stat-${String(k).toLowerCase()}`} style={{ flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md }}>
              <Txt variant="heading">{v ?? "—"}</Txt>
              <Txt variant="caption">{k}</Txt>
            </View>
          ))}
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44 }}>
          <MagnifyingGlass size={18} color={colors.muted} />
          <TextInput testID="platform-search-input" value={search} onChangeText={setSearch} placeholder="Search schools" placeholderTextColor={colors.muted} style={{ flex: 1, height: 44, fontFamily: fonts.regular, fontSize: type.base, color: colors.onSurface }} />
        </View>
      </View>
      {list.isLoading ? (
        <SkeletonList />
      ) : list.isError ? (
        <ErrorState message={(list.error as Error).message} onRetry={() => list.refetch()} />
      ) : (
        <FlatList
          testID="platform-school-list"
          data={list.data?.items}
          keyExtractor={(s) => s.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 100, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<Buildings size={40} color={colors.muted} />} title="No schools yet" message="Add your first school tenant." />}
          renderItem={({ item }) => (
            <Card testID={`tenant-card-${item.slug}`} style={{ gap: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <SchoolLogo brand={item.brand} size={44} />
                <View style={{ flex: 1 }}>
                  <Txt variant="heading" numberOfLines={1}>{item.name}</Txt>
                  <Txt variant="caption">{item.slug} · {item.contact?.city} · {item.plan}</Txt>
                </View>
                <Badge label={item.status} tone={item.status === "suspended" ? "error" : "success"} testID={`tenant-status-${item.slug}`} />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Txt variant="caption">{item.usage.students}/{item.student_quota} students · {item.usage.teachers} teachers · {item.usage.members} accounts</Txt>
              </View>
              <Button small variant={item.status === "suspended" ? "secondary" : "outline"} testID={`tenant-toggle-${item.slug}`} title={item.status === "suspended" ? "Reactivate" : "Suspend access"} onPress={() => toggle.mutate(item)} />
            </Card>
          )}
        />
      )}
      <Pressable
        testID="add-school-fab"
        onPress={() => setOpen(true)}
        style={({ pressed }) => ({ position: "absolute", right: spacing.lg, bottom: insets.bottom + spacing.lg, height: 52, paddingHorizontal: spacing.xl, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", gap: spacing.sm, transform: [{ scale: pressed ? 0.96 : 1 }], elevation: 4, shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12, shadowOffset: { width: 0, height: 6 } })}
      >
        <Plus size={18} color={colors.onBrandPrimary} weight="bold" />
        <Txt variant="label" color={colors.onBrandPrimary}>Add school</Txt>
      </Pressable>
      <Sheet visible={open} onClose={() => setOpen(false)} title="New school tenant" testID="create-school-sheet" footer={<Button testID="create-school-submit" title="Create school" loading={create.isPending} onPress={() => create.mutate()} />}>
        <Field testID="school-name-input" label="School name" value={f.name} onChangeText={(v) => setF((x) => ({ ...x, name: v, slug: x.slug || "" }))} />
        <Field testID="school-slug-input" label="Slug (url-safe)" hint="Lowercase letters, numbers and dashes" autoCapitalize="none" value={f.slug} onChangeText={(v) => set("slug")(v.toLowerCase())} />
        <Field testID="school-city-input" label="City" value={f.city} onChangeText={set("city")} />
        <Field testID="owner-name-input" label="Owner name" value={f.owner_name} onChangeText={set("owner_name")} />
        <Field testID="owner-email-input" label="Owner email" autoCapitalize="none" keyboardType="email-address" value={f.owner_email} onChangeText={set("owner_email")} />
        <Field testID="owner-password-input" label="Owner temporary password" secureTextEntry hint="At least 8 characters" value={f.owner_password} onChangeText={set("owner_password")} />
      </Sheet>
    </View>
  );
}
