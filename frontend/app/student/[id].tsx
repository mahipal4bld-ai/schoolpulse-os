import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CheckCircle, Phone, ShieldWarning, UserPlus } from "phosphor-react-native";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import type { SchoolClass } from "@/src/types";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, ErrorState, Field, Header, IconTile, LoadingState, Row, SectionTitle, Segmented, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

export default function StudentDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const sid = membership?.school_id;
  const manage = can("people.manage");
  const q = useQuery({ queryKey: ["student", sid, id], queryFn: () => api(`/students/${id}`) });
  const [linkOpen, setLinkOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [g, setG] = useState({ name: "", phone: "", email: "", relation: "mother" });

  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ["student", sid, id] });
    qc.invalidateQueries({ queryKey: ["owner-dash", sid] });
    qc.invalidateQueries({ queryKey: ["people", sid] });
    toast.show(msg);
  };
  const verify = useMutation({
    mutationFn: (p: { id: string; verified: boolean }) => api(`/guardian-links/${p.id}`, { method: "PATCH", body: { verified: p.verified } }),
    onSuccess: () => done("Guardian verification updated"),
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const link = useMutation({
    mutationFn: () => api("/guardian-links", { body: { student_id: id, relation: g.relation, guardian: { name: g.name.trim(), phone: g.phone.trim(), email: g.email.trim() || null } } }),
    onSuccess: () => {
      setLinkOpen(false);
      setG({ name: "", phone: "", email: "", relation: "mother" });
      done("Guardian linked");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const classes = useQuery({ queryKey: ["classes", sid], enabled: manage, queryFn: () => api<Paged<SchoolClass>>("/classes?page_size=100") });
  const [editOpen, setEditOpen] = useState(false);
  const [e, setE] = useState({ first_name: "", last_name: "", roll_no: "", class_id: "", section_id: "" });
  const editCls = classes.data?.items.find((c) => c.id === e.class_id);
  const edit = useMutation({
    mutationFn: () =>
      api(`/students/${id}`, {
        method: "PATCH",
        body: { first_name: e.first_name.trim(), last_name: e.last_name.trim(), roll_no: e.roll_no ? Number(e.roll_no) : null, ...(e.section_id ? { section_id: e.section_id } : {}) },
      }),
    onSuccess: () => {
      setEditOpen(false);
      done("Student updated");
    },
    onError: (err: Error) => toast.show(err.message, "error"),
  });
  const archive = useMutation({
    mutationFn: () => api(`/students/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setArchiveOpen(false);
      done("Student archived");
      router.back();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <View style={{ flex: 1 }}><Header back title="Student" /><ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /></View>;
  const s = q.data;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={`${s.first_name} ${s.last_name}`} subtitle={`${s.class_name} - ${s.section_name} · Adm. ${s.admission_no}`} />
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
        <Card testID="student-profile-card" style={{ gap: spacing.md }}>
          {[
            ["Admission no.", s.admission_no],
            ["Class & section", `${s.class_name} - ${s.section_name}`],
            ["Roll no.", s.roll_no ?? "—"],
            ["Gender", s.gender],
            ["Date of birth", formatDate(s.dob)],
            ["Status", s.status],
          ].map(([k, v]) => (
            <View key={k as string} style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Txt variant="caption">{k}</Txt>
              <Txt variant="label" style={{ textTransform: "capitalize" }}>{String(v)}</Txt>
            </View>
          ))}
        </Card>

        <View>
          <SectionTitle title="Guardians" action={manage ? <Button small variant="ghost" testID="link-guardian-button" title="Link guardian" icon={<UserPlus size={16} color={colors.brandPrimary} />} onPress={() => setLinkOpen(true)} /> : null} />
          <Card style={{ paddingVertical: 0 }}>
            {s.guardians.length === 0 ? (
              <Txt variant="caption" style={{ paddingVertical: spacing.lg }}>No guardians linked yet.</Txt>
            ) : (
              s.guardians.map((l: any, i: number) => (
                <Row
                  key={l.id}
                  testID={`guardian-link-${l.id}`}
                  last={i === s.guardians.length - 1}
                  icon={<IconTile tone={l.verified ? colors.successSoft : colors.warningSoft}>{l.verified ? <CheckCircle size={18} color={colors.success} /> : <ShieldWarning size={18} color={colors.warning} />}</IconTile>}
                  title={`${l.guardian?.name} · ${l.relation}`}
                  subtitle={`+91 ${l.guardian?.phone}${l.guardian?.user_id ? " · has app access" : ""}`}
                  right={
                    manage ? (
                      <Button small variant={l.verified ? "outline" : "secondary"} testID={`toggle-verify-${l.id}`} title={l.verified ? "Unverify" : "Verify"} onPress={() => verify.mutate({ id: l.id, verified: !l.verified })} />
                    ) : (
                      <Badge label={l.verified ? "Verified" : "Pending"} tone={l.verified ? "success" : "warning"} />
                    )
                  }
                />
              ))
            )}
          </Card>
          <Txt variant="caption" style={{ marginTop: spacing.sm }}>Only verified guardians whose email matches an app account can view this child.</Txt>
        </View>

        {manage && s.status === "active" ? (
          <Button
            testID="edit-student-button"
            variant="outline"
            title="Edit student"
            onPress={() => {
              setE({ first_name: s.first_name, last_name: s.last_name, roll_no: s.roll_no ? String(s.roll_no) : "", class_id: s.class_id, section_id: s.section_id });
              setEditOpen(true);
            }}
          />
        ) : null}
        {manage && s.status === "active" ? <Button testID="archive-student-button" variant="danger" title="Archive student" onPress={() => setArchiveOpen(true)} /> : null}
      </ScrollView>

      <Sheet visible={linkOpen} onClose={() => setLinkOpen(false)} title="Link a guardian" testID="link-guardian-sheet" footer={<Button testID="link-guardian-submit" title="Link guardian" loading={link.isPending} onPress={() => link.mutate()} />}>
        <Field testID="link-guardian-name" label="Full name" value={g.name} onChangeText={(v) => setG({ ...g, name: v })} />
        <Field testID="link-guardian-phone" label="Mobile (10 digits)" keyboardType="phone-pad" maxLength={10} value={g.phone} onChangeText={(v) => setG({ ...g, phone: v })} />
        <Field testID="link-guardian-email" label="Email (enables app access)" autoCapitalize="none" keyboardType="email-address" value={g.email} onChangeText={(v) => setG({ ...g, email: v })} />
        <Segmented testIDPrefix="link-guardian-relation" value={g.relation} onChange={(v) => setG({ ...g, relation: v })} options={[{ value: "mother", label: "Mother" }, { value: "father", label: "Father" }, { value: "guardian", label: "Guardian" }]} />
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
          <Phone size={14} color={colors.muted} />
          <Txt variant="caption">An existing guardian with the same mobile is reused.</Txt>
        </View>
      </Sheet>
      <Sheet visible={editOpen} onClose={() => setEditOpen(false)} title="Edit student" testID="edit-student-sheet" footer={<Button testID="edit-student-submit" title="Save changes" loading={edit.isPending} onPress={() => edit.mutate()} />}>
        <Field testID="edit-student-first-name" label="First name" value={e.first_name} onChangeText={(v) => setE({ ...e, first_name: v })} />
        <Field testID="edit-student-last-name" label="Last name" value={e.last_name} onChangeText={(v) => setE({ ...e, last_name: v })} />
        <Field testID="edit-student-roll" label="Roll number" keyboardType="number-pad" value={e.roll_no} onChangeText={(v) => setE({ ...e, roll_no: v })} />
        <View style={{ marginHorizontal: -spacing.xl, gap: spacing.xs }}>
          <Txt variant="label" style={{ paddingHorizontal: spacing.xl }}>Class</Txt>
          <ChipRow testIDPrefix="edit-student-class" value={e.class_id} onChange={(v) => setE({ ...e, class_id: v, section_id: "" })} options={(classes.data?.items ?? []).map((c) => ({ value: c.id, label: c.name }))} />
          {editCls ? (
            <>
              <Txt variant="label" style={{ paddingHorizontal: spacing.xl }}>Section</Txt>
              <ChipRow testIDPrefix="edit-student-section" value={e.section_id} onChange={(v) => setE({ ...e, section_id: v })} options={editCls.sections.map((x) => ({ value: x.id, label: `Section ${x.name}` }))} />
            </>
          ) : null}
        </View>
        {!e.section_id ? <Txt variant="caption" color={colors.warning}>Choose a section to move the student, or keep the current one by re-selecting it.</Txt> : null}
      </Sheet>
      <Sheet visible={archiveOpen} onClose={() => setArchiveOpen(false)} title="Archive student?" testID="archive-student-sheet" footer={<Button testID="archive-student-confirm" variant="danger" title="Archive" loading={archive.isPending} onPress={() => archive.mutate()} />}>
        <Txt variant="body">The record is retained for compliance but removed from active lists and counts.</Txt>
      </Sheet>
    </View>
  );
}
