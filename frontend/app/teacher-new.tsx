import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Button, Card, Field, Header, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function TeacherNew() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const [f, setF] = useState({ name: "", email: "", phone: "", designation: "Teacher", employee_code: "" });
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => api("/teachers", { body: { ...f, name: f.name.trim(), email: f.email.trim(), phone: f.phone.trim() } }),
    onSuccess: (t: any) => {
      qc.invalidateQueries({ queryKey: ["people", membership?.school_id] });
      qc.invalidateQueries({ queryKey: ["owner-dash", membership?.school_id] });
      toast.show("Teacher added");
      router.replace(`/teacher/${t.id}`);
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="New teacher" />
      <KeyboardAwareScrollView bottomOffset={96} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
        <Card style={{ gap: spacing.lg }}>
          <Field testID="teacher-name-input" label="Full name" value={f.name} onChangeText={set("name")} />
          <Field testID="teacher-email-input" label="Email" autoCapitalize="none" keyboardType="email-address" value={f.email} onChangeText={set("email")} />
          <Field testID="teacher-phone-input" label="Mobile (10 digits)" keyboardType="phone-pad" maxLength={10} value={f.phone} onChangeText={set("phone")} />
          <Field testID="teacher-designation-input" label="Designation" value={f.designation} onChangeText={set("designation")} />
          <Field testID="teacher-code-input" label="Employee code" autoCapitalize="characters" value={f.employee_code} onChangeText={set("employee_code")} />
        </Card>
        <Txt variant="caption">To give this teacher app access, send a staff invitation to the same email from Settings.</Txt>
      </KeyboardAwareScrollView>
      <KeyboardStickyView offset={{ opened: insets.bottom }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="teacher-save-button" title="Create teacher" loading={save.isPending} onPress={() => save.mutate()} />
        </View>
      </KeyboardStickyView>
    </View>
  );
}
