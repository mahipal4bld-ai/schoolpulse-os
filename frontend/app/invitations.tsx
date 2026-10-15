import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EnvelopeSimple } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate, ROLE_LABEL } from "@/src/format";
import { fonts, spacing, useTheme } from "@/src/theme";

const ROLES = ["teacher", "principal", "school_admin", "accountant", "admission_coordinator", "transport_coordinator"];

export default function Invitations() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["invites", membership?.school_id];
  const q = useQuery({ queryKey: key, queryFn: () => api<{ items: any[] }>("/invitations") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", email: "", role: "teacher" });
  const create = useMutation({
    mutationFn: () => api("/invitations", { body: { name: f.name.trim(), email: f.email.trim(), role: f.role } }),
    onSuccess: () => {
      setOpen(false);
      setF({ name: "", email: "", role: "teacher" });
      qc.invalidateQueries({ queryKey: key });
      toast.show("Invitation created. Share the code with the staff member.");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api(`/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Staff invitations" right={<Button small testID="new-invite-button" title="Invite" onPress={() => setOpen(true)} />} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          data={q.data?.items}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListHeaderComponent={<Txt variant="caption">Email/SMS delivery is not connected in this milestone. Share the code securely; the staff member enters it on the sign-in screen.</Txt>}
          ListEmptyComponent={<EmptyState icon={<EnvelopeSimple size={40} color={colors.muted} />} title="No invitations yet" />}
          renderItem={({ item }) => (
            <Card testID={`invite-card-${item.email}`} style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Txt variant="label">{item.name}</Txt>
                <Badge label={item.status} tone={item.status === "pending" ? "warning" : item.status === "accepted" ? "success" : "neutral"} />
              </View>
              <Txt variant="caption">{item.email} · {ROLE_LABEL[item.role]} · expires {formatDate(item.expires_at)}</Txt>
              {item.status === "pending" ? (
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                  <Txt selectable testID={`invite-code-${item.email}`} style={{ fontFamily: fonts.medium, letterSpacing: 1 }} color={colors.brandPrimary}>{item.token}</Txt>
                  <Button small variant="ghost" testID={`revoke-invite-${item.email}`} title="Revoke" onPress={() => revoke.mutate(item.id)} />
                </View>
              ) : null}
            </Card>
          )}
        />
      )}
      <Sheet visible={open} onClose={() => setOpen(false)} title="Invite staff" testID="invite-sheet" footer={<Button testID="invite-submit" title="Create invitation" loading={create.isPending} onPress={() => create.mutate()} />}>
        <Field testID="invite-staff-name" label="Full name" value={f.name} onChangeText={(v) => setF({ ...f, name: v })} />
        <Field testID="invite-staff-email" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.email} onChangeText={(v) => setF({ ...f, email: v })} />
        <View style={{ marginHorizontal: -spacing.xl }}>
          <ChipRow testIDPrefix="invite-role" value={f.role} onChange={(v) => setF({ ...f, role: v })} options={ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r] }))} />
        </View>
      </Sheet>
    </View>
  );
}
