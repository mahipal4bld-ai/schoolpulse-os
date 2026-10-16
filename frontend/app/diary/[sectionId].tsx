import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { NotePencil, PencilSimple, Plus, Trash } from "phosphor-react-native";
import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { DayStepper, DiaryEntry, DiaryItem } from "@/src/components/diary";
import { isoDay } from "@/src/components/homework";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type Opt = { section_id: string; label: string; subjects: { id: string; name: string }[] };
type Form = { id?: string; kind: "lesson" | "note"; subject_id: string; topic: string; summary: string };

export default function SectionDiary() {
  const { sectionId } = useLocalSearchParams<{ sectionId: string }>();
  const { membership, me, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const [day, setDay] = useState(isoDay());
  const [form, setForm] = useState<Form | null>(null);
  const [del, setDel] = useState<DiaryEntry | null>(null);
  const key = ["diary", membership?.school_id, sectionId, day];
  const q = useQuery({ queryKey: key, queryFn: () => api<{ section: string; date: string; items: DiaryEntry[] }>(`/diary?section_id=${sectionId}&date=${day}`) });
  const opts = useQuery({ queryKey: ["homework-options"], queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const subjects = opts.data?.items.find((o) => o.section_id === sectionId)?.subjects ?? [];
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["diary", membership?.school_id, sectionId] });
    qc.invalidateQueries({ queryKey: ["diary-summary"] });
  };
  const save = useMutation({
    mutationFn: () =>
      form!.id
        ? api(`/diary/${form!.id}`, { method: "PATCH", body: { topic: form!.topic, summary: form!.summary } })
        : api("/diary", { body: { section_id: sectionId, date: day, kind: form!.kind, subject_id: form!.kind === "lesson" ? form!.subject_id : null, topic: form!.topic, summary: form!.summary } }),
    onSuccess: () => {
      toast.show(form?.id ? "Diary entry updated" : "Added to class diary");
      setForm(null);
      refresh();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const remove = useMutation({
    mutationFn: () => api(`/diary/${del!.id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.show("Diary entry deleted");
      setDel(null);
      refresh();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const mine = (e: DiaryEntry) => can("academic.manage") || e.created_by === me?.user.id;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Class diary" subtitle={q.data?.section} />
      <View style={{ paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <DayStepper value={day} onChange={setDay} />
      </View>
      {q.isLoading ? <SkeletonList rows={3} /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, flexGrow: 1 }}>
          {q.data!.items.length ? (
            <Card style={{ paddingVertical: spacing.xs }} testID="diary-list">
              {q.data!.items.map((e) => (
                <DiaryItem
                  key={e.id}
                  e={e}
                  right={mine(e) ? (
                    <View style={{ gap: spacing.xs }}>
                      <Pressable testID={`diary-edit-${e.id}`} hitSlop={6} onPress={() => setForm({ id: e.id, kind: e.kind, subject_id: e.subject_id ?? "", topic: e.topic, summary: e.summary })} style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center" }}><PencilSimple size={18} color={colors.muted} /></Pressable>
                      <Pressable testID={`diary-delete-${e.id}`} hitSlop={6} onPress={() => setDel(e)} style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center" }}><Trash size={18} color={colors.muted} /></Pressable>
                    </View>
                  ) : null}
                />
              ))}
            </Card>
          ) : (
            <EmptyState icon={<NotePencil size={40} color={colors.muted} />} title="Nothing written for this day" message="Add what was taught today so parents can follow along." />
          )}
        </ScrollView>
      )}
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Button testID="diary-add-button" title="Add diary entry" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setForm({ kind: subjects.length ? "lesson" : "note", subject_id: subjects[0]?.id ?? "", topic: "", summary: "" })} />
      </View>
      <Sheet visible={!!form} onClose={() => setForm(null)} testID="diary-sheet" title={form?.id ? "Edit entry" : "New diary entry"} footer={<Button testID="diary-save" title="Save" loading={save.isPending} onPress={() => save.mutate()} />}>
        {form && !form.id ? (
          <>
            <Segmented testIDPrefix="diary-kind" value={form.kind} onChange={(kind) => setForm({ ...form, kind })} options={[{ value: "lesson", label: "Lesson" }, { value: "note", label: "Class note" }]} />
            {form.kind === "lesson" ? (
              <View style={{ marginHorizontal: -spacing.lg }}>
                <ChipRow testIDPrefix="diary-subject" value={form.subject_id} onChange={(subject_id) => setForm({ ...form, subject_id })} options={subjects.map((s) => ({ value: s.id, label: s.name }))} />
              </View>
            ) : null}
          </>
        ) : null}
        {form ? (
          <>
            <Field testID="diary-topic-input" label={form.kind === "lesson" ? "Topic taught" : "Note"} value={form.topic} onChangeText={(topic) => setForm({ ...form, topic })} placeholder={form.kind === "lesson" ? "e.g. Photosynthesis – introduction" : "e.g. Bring crayons tomorrow"} />
            <Field testID="diary-summary-input" label="Details (optional)" value={form.summary} onChangeText={(summary) => setForm({ ...form, summary })} placeholder="e.g. Covered chlorophyll, did the leaf experiment" multiline style={{ minHeight: 80, textAlignVertical: "top" }} />
          </>
        ) : null}
      </Sheet>
      <Sheet visible={!!del} onClose={() => setDel(null)} title="Delete entry?" testID="diary-delete-sheet" footer={<Button testID="diary-delete-confirm" variant="danger" title="Delete" loading={remove.isPending} onPress={() => remove.mutate()} />}>
        <Txt variant="body">Parents will no longer see this entry.</Txt>
      </Sheet>
    </View>
  );
}
