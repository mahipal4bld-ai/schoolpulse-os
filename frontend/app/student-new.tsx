import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Button, Card, ChipRow, Field, Header, SectionTitle, Segmented, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";
import type { SchoolClass } from "@/src/types";

export default function StudentNew() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const sid = membership?.school_id;
  const classes = useQuery({ queryKey: ["classes", sid], queryFn: () => api<Paged<SchoolClass>>("/classes?page_size=100") });
  const [f, setF] = useState({ admission_no: "", first_name: "", last_name: "", gender: "female", dob: "", class_id: "", section_id: "", roll_no: "", g_name: "", g_phone: "", g_relation: "mother" });
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const cls = classes.data?.items.find((c) => c.id === f.class_id);

  const save = useMutation({
    mutationFn: async () => {
      if (!f.section_id) throw new Error("Choose a class and section");
      const s = await api("/students", {
        body: { admission_no: f.admission_no.trim(), first_name: f.first_name.trim(), last_name: f.last_name.trim(), gender: f.gender, dob: f.dob.trim(), section_id: f.section_id, roll_no: f.roll_no ? Number(f.roll_no) : null },
      });
      if (f.g_name.trim() && f.g_phone.trim()) {
        await api("/guardian-links", { body: { student_id: s.id, relation: f.g_relation, guardian: { name: f.g_name.trim(), phone: f.g_phone.trim() } } });
      }
      return s;
    },
    onSuccess: (s: any) => {
      qc.invalidateQueries({ queryKey: ["people", sid] });
      qc.invalidateQueries({ queryKey: ["owner-dash", sid] });
      toast.show("Student added");
      router.replace(`/student/${s.id}`);
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="New student" subtitle={`Session ${membership?.school.academic_session_label ?? ""}`} />
      <KeyboardAwareScrollView bottomOffset={96} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Student" />
          <Field testID="student-admission-input" label="Admission number" autoCapitalize="characters" value={f.admission_no} onChangeText={set("admission_no")} placeholder="SV2001" />
          <Field testID="student-first-name-input" label="First name" value={f.first_name} onChangeText={set("first_name")} />
          <Field testID="student-last-name-input" label="Last name" value={f.last_name} onChangeText={set("last_name")} />
          <View style={{ gap: spacing.sm }}>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Gender</Txt>
            <Segmented testIDPrefix="student-gender" value={f.gender} onChange={set("gender")} options={[{ value: "female", label: "Female" }, { value: "male", label: "Male" }, { value: "other", label: "Other" }]} />
          </View>
          <Field testID="student-dob-input" label="Date of birth (YYYY-MM-DD)" value={f.dob} onChangeText={set("dob")} placeholder="2016-08-14" />
          <Field testID="student-roll-input" label="Roll number (optional)" keyboardType="number-pad" value={f.roll_no} onChangeText={set("roll_no")} />
        </Card>
        <Card style={{ gap: spacing.md, paddingHorizontal: 0 }}>
          <View style={{ paddingHorizontal: spacing.lg }}>
            <SectionTitle title="Class placement" />
          </View>
          <ChipRow testIDPrefix="student-class" value={f.class_id} onChange={(v) => setF((x) => ({ ...x, class_id: v, section_id: "" }))} options={(classes.data?.items ?? []).map((c) => ({ value: c.id, label: c.name }))} />
          {cls ? (
            <ChipRow testIDPrefix="student-section" value={f.section_id} onChange={set("section_id")} options={cls.sections.map((s) => ({ value: s.id, label: `Section ${s.name}` }))} />
          ) : (
            <Txt variant="caption" style={{ paddingHorizontal: spacing.lg }}>Choose a class to see its sections.</Txt>
          )}
        </Card>
        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Primary guardian (optional)" />
          <Field testID="guardian-name-input" label="Guardian name" value={f.g_name} onChangeText={set("g_name")} />
          <Field testID="guardian-phone-input" label="Mobile (10 digits)" keyboardType="phone-pad" maxLength={10} value={f.g_phone} onChangeText={set("g_phone")} />
          <Segmented testIDPrefix="guardian-relation" value={f.g_relation} onChange={set("g_relation")} options={[{ value: "mother", label: "Mother" }, { value: "father", label: "Father" }, { value: "guardian", label: "Guardian" }]} />
          <Txt variant="caption">The link starts unverified. Verify it on the student page after checking documents.</Txt>
        </Card>
      </KeyboardAwareScrollView>
      <KeyboardStickyView offset={{ opened: insets.bottom }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="student-save-button" title="Create student" loading={save.isPending} onPress={() => save.mutate()} />
        </View>
      </KeyboardStickyView>
    </View>
  );
}
