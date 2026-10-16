import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Exam as ExamIcon, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { ExamT, STATUS_LABEL } from "@/src/components/exams";
import { isoDay } from "@/src/components/homework";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

type Opt = { section_id: string; label: string; subjects: { id: string; name: string }[] };

function Toggle({ on, label, onPress, testID }: { on: boolean; label: string; onPress: () => void; testID: string }) {
  const { colors } = useTheme();
  return (
    <Pressable testID={testID} onPress={onPress} style={{ minHeight: 36, paddingHorizontal: spacing.md, justifyContent: "center", borderRadius: radius.pill, borderWidth: 1, borderColor: on ? colors.brandPrimary : colors.border, backgroundColor: on ? colors.brandPrimary : colors.surface }}>
      <Txt variant="caption" raw color={on ? colors.onBrandPrimary : colors.onSurface}>{label}</Txt>
    </Pressable>
  );
}

export default function ExamsList() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const manage = can("academic.manage");
  const q = useQuery({ queryKey: ["exams", membership?.school_id], queryFn: () => api<{ items: ExamT[] }>("/exams") });
  const opts = useQuery({ queryKey: ["homework-options"], enabled: manage, queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", term: "", start: isoDay(), end: isoDay(7), max: "100", pass: "33" });
  const [secs, setSecs] = useState<string[]>([]);
  const [subs, setSubs] = useState<string[]>([]);
  const toggle = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const create = useMutation({
    mutationFn: () => api<ExamT>("/exams", { body: { name: f.name, term: f.term, start_date: f.start, end_date: f.end, section_ids: secs, subjects: subs.map((subject_id) => ({ subject_id, max_marks: Number(f.max), pass_marks: Number(f.pass) })) } }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["exams"] });
      setOpen(false);
      toast.show("Exam created · marks entry is open");
      router.push(`/exams/${d.id}`);
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const allSubjects = opts.data?.items[0]?.subjects ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Examinations" />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="exams-list"
          data={q.data!.items}
          keyExtractor={(e) => e.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<ExamIcon size={40} color={colors.muted} />} title="No exams yet" message={manage ? "Create an exam to open marks entry for teachers." : "Exams for your sections appear here."} />}
          renderItem={({ item }) => (
            <Pressable testID={`exam-card-${item.id}`} onPress={() => router.push(`/exams/${item.id}`)}>
              <Card style={{ gap: spacing.xs }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{item.name}</Txt>
                  <Badge tone={item.status === "published" ? "success" : "warning"} label={STATUS_LABEL[item.status]} />
                </View>
                <Txt variant="caption" raw>{item.term ? `${item.term} · ` : ""}{formatDate(item.start_date)} – {formatDate(item.end_date)}</Txt>
                <Txt variant="caption" raw>Marks entered {item.progress.entered}/{item.progress.total}</Txt>
              </Card>
            </Pressable>
          )}
        />
      )}
      {manage ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="new-exam-button" title="New exam" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setOpen(true)} />
        </View>
      ) : null}
      <Sheet visible={open} onClose={() => setOpen(false)} title="New exam" testID="new-exam-sheet" footer={<Button testID="exam-create-submit" title="Create exam" loading={create.isPending} onPress={() => create.mutate()} />}>
        <Field testID="exam-name-input" label="Exam name" value={f.name} onChangeText={(name) => setF({ ...f, name })} placeholder="e.g. Unit Test 1" />
        <Field testID="exam-term-input" label="Term (optional)" value={f.term} onChangeText={(term) => setF({ ...f, term })} placeholder="e.g. Term 1" />
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <View style={{ flex: 1 }}><Field testID="exam-start-input" label="Starts" value={f.start} onChangeText={(start) => setF({ ...f, start })} autoCapitalize="none" /></View>
          <View style={{ flex: 1 }}><Field testID="exam-end-input" label="Ends" value={f.end} onChangeText={(end) => setF({ ...f, end })} autoCapitalize="none" /></View>
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <View style={{ flex: 1 }}><Field testID="exam-max-input" label="Max marks" keyboardType="number-pad" value={f.max} onChangeText={(max) => setF({ ...f, max })} /></View>
          <View style={{ flex: 1 }}><Field testID="exam-pass-input" label="Pass marks" keyboardType="number-pad" value={f.pass} onChangeText={(pass) => setF({ ...f, pass })} /></View>
        </View>
        <Txt variant="label" color={colors.onSurfaceTertiary}>Sections ({secs.length})</Txt>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {(opts.data?.items ?? []).map((o) => <Toggle key={o.section_id} testID={`exam-sec-${o.section_id}`} on={secs.includes(o.section_id)} label={o.label} onPress={() => toggle(secs, setSecs, o.section_id)} />)}
        </View>
        <Txt variant="label" color={colors.onSurfaceTertiary}>Subjects ({subs.length})</Txt>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
          {allSubjects.map((s) => <Toggle key={s.id} testID={`exam-sub-${s.id}`} on={subs.includes(s.id)} label={s.name} onPress={() => toggle(subs, setSubs, s.id)} />)}
        </View>
      </Sheet>
    </View>
  );
}
