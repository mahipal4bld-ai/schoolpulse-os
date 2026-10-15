import { useMutation } from "@tanstack/react-query";
import React, { useState } from "react";
import { View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Button, Card, Field, Header, SectionTitle, Segmented, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function SchoolProfile() {
  const { membership, can, refresh } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const s = membership!.school;
  const editable = can("school.manage");
  const [f, setF] = useState({
    name: s.name,
    description: s.description ?? "",
    board: s.board ?? "",
    preferred_language: (s.preferred_language ?? "en") as "en" | "hi",
    custom_domain: s.custom_domain ?? "",
    contact: { phone: "", email: "", address: "", city: "", state: "", pincode: "", website: "", map_url: "", ...s.contact },
    operating: { start_time: "08:00", end_time: "14:00", working_days: "Mon-Sat", ...s.operating },
  });
  const c = (k: keyof typeof f.contact) => (v: string) => setF({ ...f, contact: { ...f.contact, [k]: v } });
  const o = (k: keyof typeof f.operating) => (v: string) => setF({ ...f, operating: { ...f.operating, [k]: v } });

  const save = useMutation({
    mutationFn: async () => {
      await api("/school/settings", { method: "PATCH", body: f });
      await refresh();
    },
    onSuccess: () => toast.show("School profile saved"),
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="School profile" subtitle={editable ? "Changes are saved to your school record" : "View only for your role"} />
      <KeyboardAwareScrollView bottomOffset={96} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Identity" />
          <Field testID="profile-name-input" editable={editable} label="Official school name" value={f.name} onChangeText={(v) => setF({ ...f, name: v })} />
          <Field testID="profile-description-input" editable={editable} multiline label="Description" value={f.description} onChangeText={(v) => setF({ ...f, description: v })} />
          <Field testID="profile-board-input" editable={editable} label="Board / affiliation" value={f.board} onChangeText={(v) => setF({ ...f, board: v })} />
          <View style={{ gap: spacing.sm }}>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Preferred school language</Txt>
            <Segmented testIDPrefix="profile-language" value={f.preferred_language} onChange={(v) => editable && setF({ ...f, preferred_language: v })} options={[{ value: "en", label: "English" }, { value: "hi", label: "हिंदी" }]} />
          </View>
          <Txt variant="caption">Academic session: {s.academic_session_label || "—"} (change it in Academics)</Txt>
        </Card>
        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Contact & location" />
          <Field testID="profile-phone-input" editable={editable} label="Phone" keyboardType="phone-pad" value={f.contact.phone} onChangeText={c("phone")} />
          <Field testID="profile-email-input" editable={editable} label="Email" autoCapitalize="none" keyboardType="email-address" value={f.contact.email} onChangeText={c("email")} />
          <Field testID="profile-address-input" editable={editable} label="Address" value={f.contact.address} onChangeText={c("address")} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <Field testID="profile-city-input" editable={editable} label="City" value={f.contact.city} onChangeText={c("city")} />
            </View>
            <View style={{ flex: 1 }}>
              <Field testID="profile-pincode-input" editable={editable} label="PIN code" keyboardType="number-pad" value={f.contact.pincode} onChangeText={c("pincode")} />
            </View>
          </View>
          <Field testID="profile-state-input" editable={editable} label="State" value={f.contact.state} onChangeText={c("state")} />
          <Field testID="profile-website-input" editable={editable} label="Website" autoCapitalize="none" value={f.contact.website} onChangeText={c("website")} />
          <Field testID="profile-map-input" editable={editable} label="Map link" autoCapitalize="none" value={f.contact.map_url} onChangeText={c("map_url")} />
          <Field testID="profile-domain-input" editable={editable} label="Custom domain (optional)" hint="DNS setup is handled in a later milestone" autoCapitalize="none" value={f.custom_domain} onChangeText={(v) => setF({ ...f, custom_domain: v })} />
        </Card>
        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Operating details" />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <Field testID="profile-start-input" editable={editable} label="Opens (HH:MM)" value={f.operating.start_time} onChangeText={o("start_time")} />
            </View>
            <View style={{ flex: 1 }}>
              <Field testID="profile-end-input" editable={editable} label="Closes (HH:MM)" value={f.operating.end_time} onChangeText={o("end_time")} />
            </View>
          </View>
          <Field testID="profile-days-input" editable={editable} label="Working days" value={f.operating.working_days} onChangeText={o("working_days")} />
        </Card>
      </KeyboardAwareScrollView>
      {editable ? (
        <KeyboardStickyView offset={{ opened: insets.bottom }}>
          <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
            <Button testID="profile-save-button" title="Save profile" loading={save.isPending} onPress={() => save.mutate()} />
          </View>
        </KeyboardStickyView>
      ) : null}
    </View>
  );
}
