import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { Chalkboard, Trash } from "phosphor-react-native";
import React, { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, ErrorState, Header, IconTile, LoadingState, Row, SectionTitle, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";
import type { SchoolClass, Teacher } from "@/src/types";

export default function TeacherDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const sid = membership?.school_id;
  const manage = can("academic.manage");
  const q = useQuery({ queryKey: ["teacher", sid, id], queryFn: () => api<Teacher>(`/teachers/${id}`) });
  const classes = useQuery({ queryKey: ["classes", sid], queryFn: () => api<Paged<SchoolClass>>("/classes?page_size=100") });
  const subjects = useQuery({ queryKey: ["subjects", sid], queryFn: () => api<Paged<{ id: string; name: string }>>("/subjects?page_size=100") });
  const [open, setOpen] = useState(false);
  const [a, setA] = useState({ class_id: "", section_id: "", subject_id: "", ct: "no" });
  const cls = classes.data?.items.find((c) => c.id === a.class_id);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["teacher", sid, id] });
    qc.invalidateQueries({ queryKey: ["people", sid] });
  };
  const add = useMutation({
    mutationFn: () => {
      if (!a.section_id) throw new Error("Choose a class and section");
      return api("/teacher-assignments", { body: { teacher_id: id, section_id: a.section_id, subject_id: a.subject_id || null, is_class_teacher: a.ct === "yes" } });
    },
    onSuccess: () => {
      setOpen(false);
      setA({ class_id: "", section_id: "", subject_id: "", ct: "no" });
      refresh();
      toast.show("Assignment added");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const remove = useMutation({
    mutationFn: (aid: string) => api(`/teacher-assignments/${aid}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      toast.show("Assignment removed");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Teacher" /><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></View>;
  const t = q.data!;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={t.name} subtitle={`${t.designation}${t.employee_code ? ` · ${t.employee_code}` : ""}`} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
        <Card style={{ gap: spacing.md }} testID="teacher-profile-card">
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Txt variant="caption">Email</Txt><Txt variant="label">{t.email}</Txt></View>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Txt variant="caption">Mobile</Txt><Txt variant="label">+91 {t.phone}</Txt></View>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Txt variant="caption">App access</Txt><Badge label={t.user_id ? "Active" : "Not invited"} tone={t.user_id ? "success" : "neutral"} /></View>
        </Card>
        <View>
          <SectionTitle title="Class assignments" action={manage ? <Button small variant="ghost" testID="add-assignment-button" title="Assign" onPress={() => setOpen(true)} /> : null} />
          <Card style={{ paddingVertical: 0 }}>
            {t.assignments.length === 0 ? (
              <Txt variant="caption" style={{ paddingVertical: spacing.lg }}>No classes assigned yet.</Txt>
            ) : (
              t.assignments.map((x, i) => (
                <Row
                  key={x.id}
                  testID={`assignment-row-${x.id}`}
                  last={i === t.assignments.length - 1}
                  icon={<IconTile><Chalkboard size={18} color={colors.onBrandTertiary} /></IconTile>}
                  title={x.section_label}
                  subtitle={[x.subject_name, x.is_class_teacher ? "Class teacher" : null].filter(Boolean).join(" · ") || "General"}
                  right={manage ? (
                    <Pressable testID={`remove-assignment-${x.id}`} hitSlop={8} style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center" }} onPress={() => remove.mutate(x.id)}>
                      <Trash size={18} color={colors.muted} />
                    </Pressable>
                  ) : undefined}
                />
              ))
            )}
          </Card>
        </View>
      </ScrollView>
      <Sheet visible={open} onClose={() => setOpen(false)} title="Assign class" testID="assignment-sheet" footer={<Button testID="assignment-submit" title="Save assignment" loading={add.isPending} onPress={() => add.mutate()} />}>
        <View style={{ marginHorizontal: -spacing.xl, gap: spacing.xs }}>
          <Txt variant="label" style={{ paddingHorizontal: spacing.xl }}>Class</Txt>
          <ChipRow testIDPrefix="assign-class" value={a.class_id} onChange={(v) => setA({ ...a, class_id: v, section_id: "" })} options={(classes.data?.items ?? []).map((c) => ({ value: c.id, label: c.name }))} />
          {cls ? (
            <>
              <Txt variant="label" style={{ paddingHorizontal: spacing.xl }}>Section</Txt>
              <ChipRow testIDPrefix="assign-section" value={a.section_id} onChange={(v) => setA({ ...a, section_id: v })} options={cls.sections.map((s) => ({ value: s.id, label: s.name }))} />
            </>
          ) : null}
          <Txt variant="label" style={{ paddingHorizontal: spacing.xl }}>Subject</Txt>
          <ChipRow testIDPrefix="assign-subject" value={a.subject_id} onChange={(v) => setA({ ...a, subject_id: v })} options={[{ value: "", label: "None" }, ...(subjects.data?.items ?? []).map((s) => ({ value: s.id, label: s.name }))]} />
        </View>
        <Row testID="assign-class-teacher-toggle" last title="Class teacher for this section" right={<Badge label={a.ct === "yes" ? "Yes" : "No"} tone={a.ct === "yes" ? "success" : "neutral"} />} onPress={() => setA({ ...a, ct: a.ct === "yes" ? "no" : "yes" })} />
      </Sheet>
    </View>
  );
}
