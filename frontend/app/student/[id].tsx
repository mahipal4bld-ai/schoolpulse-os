import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CheckCircle, Phone, ShieldWarning, UserPlus } from "phosphor-react-native";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Field, Header, IconTile, LoadingState, Row, SectionTitle, Segmented, Txt } from "@/src/components/ui";
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
      <Sheet visible={archiveOpen} onClose={() => setArchiveOpen(false)} title="Archive student?" testID="archive-student-sheet" footer={<Button testID="archive-student-confirm" variant="danger" title="Archive" loading={archive.isPending} onPress={() => archive.mutate()} />}>
        <Txt variant="body">The record is retained for compliance but removed from active lists and counts.</Txt>
      </Sheet>
    </View>
  );
}
