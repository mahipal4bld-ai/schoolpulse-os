import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarBlank, Plus, Trash } from "phosphor-react-native";
import React, { useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Field, Header, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { radius, spacing, useTheme } from "@/src/theme";
import type { SchoolClass } from "@/src/types";

type Year = { id: string; name: string; start_date: string; end_date: string; is_current: boolean };
type Subject = { id: string; name: string; code: string };
type SheetKind = null | { kind: "year" } | { kind: "class" } | { kind: "section"; cls: SchoolClass } | { kind: "subject" } | { kind: "confirm"; label: string; path: string };

export default function Academics() {
  const { membership, can } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const sid = membership?.school_id;
  const manage = can("academic.manage");
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  const years = useQuery({ queryKey: ["years", sid], queryFn: () => api<Paged<Year>>("/academic-years?page_size=50") });
  const current = years.data?.items.find((y) => y.is_current) ?? years.data?.items[0];
  const classes = useQuery({
    queryKey: ["classes", sid, current?.id],
    enabled: !!current,
    queryFn: () => api<Paged<SchoolClass>>(`/classes?page_size=100&academic_year_id=${current!.id}`),
  });
  const subjects = useQuery({ queryKey: ["subjects", sid], queryFn: () => api<Paged<Subject>>("/subjects?page_size=100") });

  const [sheet, setSheet] = useState<SheetKind>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const set = (k: string) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["years", sid] });
    qc.invalidateQueries({ queryKey: ["classes", sid] });
    qc.invalidateQueries({ queryKey: ["subjects", sid] });
    qc.invalidateQueries({ queryKey: ["owner-dash", sid] });
  };

  const mut = useMutation({
    mutationFn: async () => {
      if (!sheet) return;
      if (sheet.kind === "year")
        return api("/academic-years", { body: { name: form.name, start_date: form.start, end_date: form.end, is_current: form.current === "yes" } });
      if (sheet.kind === "class") return api("/classes", { body: { name: form.name, academic_year_id: current?.id, order: Number(form.order || 0) } });
      if (sheet.kind === "section") return api("/sections", { body: { class_id: sheet.cls.id, name: form.name, capacity: Number(form.capacity || 40) } });
      if (sheet.kind === "subject") return api("/subjects", { body: { name: form.name, code: form.code } });
      if (sheet.kind === "confirm") return api(sheet.path, { method: "DELETE" });
    },
    onSuccess: () => {
      toast.show(sheet?.kind === "confirm" ? "Deleted" : "Saved");
      setSheet(null);
      setForm({});
      refresh();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  const setCurrent = useMutation({
    mutationFn: (id: string) => api(`/academic-years/${id}`, { method: "PATCH", body: { is_current: true } }),
    onSuccess: () => {
      toast.show("Current academic year updated");
      refresh();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  const open = (s: SheetKind, init: Record<string, string> = {}) => {
    setForm(init);
    setSheet(s);
  };

  const AddBtn = ({ onPress, testID }: { onPress: () => void; testID: string }) =>
    manage ? (
      <Pressable testID={testID} onPress={onPress} hitSlop={8} style={{ flexDirection: "row", alignItems: "center", gap: 4, minHeight: 32 }}>
        <Plus size={14} color={colors.brandPrimary} weight="bold" />
        <Txt variant="label" color={colors.brandPrimary}>
          Add
        </Txt>
      </Pressable>
    ) : null;

  const loading = years.isLoading || subjects.isLoading;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header title={t("academics")} subtitle={current ? `Session ${current.name}` : undefined} />
      {loading ? (
        <SkeletonList />
      ) : years.isError ? (
        <ErrorState message={(years.error as Error).message} onRetry={refresh} />
      ) : (
        <ScrollView
          refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}
        >
          <View>
            <SectionTitle title={t("academicYears")} action={<AddBtn testID="add-year-button" onPress={() => open({ kind: "year" }, { current: "yes" })} />} />
            <Card style={{ paddingVertical: 0 }}>
              {years.data?.items.length ? (
                years.data.items.map((y, i) => (
                  <Row
                    key={y.id}
                    testID={`year-row-${y.name}`}
                    last={i === years.data!.items.length - 1}
                    icon={<IconTile><CalendarBlank size={18} color={colors.onBrandTertiary} /></IconTile>}
                    title={y.name}
                    subtitle={`${formatDate(y.start_date)} – ${formatDate(y.end_date)}`}
                    right={
                      y.is_current ? (
                        <Badge label="Current" tone="success" />
                      ) : manage ? (
                        <Button small variant="outline" title="Make current" testID={`make-current-${y.name}`} onPress={() => setCurrent.mutate(y.id)} />
                      ) : undefined
                    }
                  />
                ))
              ) : (
                <Txt variant="caption" style={{ paddingVertical: spacing.lg }}>
                  No academic year yet. Add one to begin.
                </Txt>
              )}
            </Card>
          </View>

          <View>
            <SectionTitle title={`${t("classes")} & ${t("sections")}`} action={current ? <AddBtn testID="add-class-button" onPress={() => open({ kind: "class" })} /> : null} />
            <View style={{ gap: spacing.md }}>
              {classes.isLoading ? (
                <SkeletonList rows={3} />
              ) : classes.data?.items.length ? (
                classes.data.items.map((c) => (
                  <Card key={c.id} testID={`class-card-${c.name}`} style={{ gap: spacing.md }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                      <View style={{ flex: 1 }}>
                        <Txt variant="heading">{c.name}</Txt>
                        <Txt variant="caption">
                          {c.student_count} students · {c.sections.length} sections
                        </Txt>
                      </View>
                      {manage ? (
                        <Pressable testID={`delete-class-${c.name}`} hitSlop={8} style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center" }} onPress={() => open({ kind: "confirm", label: c.name, path: `/classes/${c.id}` })}>
                          <Trash size={18} color={colors.muted} />
                        </Pressable>
                      ) : null}
                    </View>
                    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                      {c.sections.map((s) => (
                        <Pressable
                          key={s.id}
                          testID={`section-chip-${c.name}-${s.name}`}
                          disabled={!manage}
                          onLongPress={() => open({ kind: "confirm", label: `${c.name} - ${s.name}`, path: `/sections/${s.id}` })}
                          style={{ height: 36, minWidth: 48, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}
                        >
                          <Txt variant="label" color={colors.onBrandTertiary}>
                            {s.name}
                          </Txt>
                        </Pressable>
                      ))}
                      {manage ? (
                        <Pressable
                          testID={`add-section-${c.name}`}
                          onPress={() => open({ kind: "section", cls: c }, { capacity: "40" })}
                          style={{ height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderStyle: "dashed", borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 4 }}
                        >
                          <Plus size={12} color={colors.muted} />
                          <Txt variant="caption">Section</Txt>
                        </Pressable>
                      ) : null}
                    </View>
                  </Card>
                ))
              ) : (
                <Card>
                  <Txt variant="caption">No classes in this session yet.</Txt>
                </Card>
              )}
              {manage && classes.data?.items.length ? <Txt variant="caption">Tip: long-press a section to delete it.</Txt> : null}
            </View>
          </View>

          <View>
            <SectionTitle title={t("subjects")} action={<AddBtn testID="add-subject-button" onPress={() => open({ kind: "subject" })} />} />
            <Card style={{ paddingVertical: 0 }}>
              {subjects.data?.items.map((s, i) => (
                <Row
                  key={s.id}
                  testID={`subject-row-${s.code}`}
                  last={i === subjects.data!.items.length - 1}
                  title={s.name}
                  subtitle={s.code}
                  right={
                    manage ? (
                      <Pressable testID={`delete-subject-${s.code}`} hitSlop={8} style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center" }} onPress={() => open({ kind: "confirm", label: s.name, path: `/subjects/${s.id}` })}>
                        <Trash size={18} color={colors.muted} />
                      </Pressable>
                    ) : undefined
                  }
                />
              ))}
              {!subjects.data?.items.length ? (
                <Txt variant="caption" style={{ paddingVertical: spacing.lg }}>
                  No subjects yet.
                </Txt>
              ) : null}
            </Card>
          </View>
        </ScrollView>
      )}

      <Sheet
        visible={!!sheet}
        onClose={() => setSheet(null)}
        testID="academics-sheet"
        title={
          sheet?.kind === "year" ? "New academic year" : sheet?.kind === "class" ? "New class" : sheet?.kind === "section" ? `New section · ${sheet.cls.name}` : sheet?.kind === "subject" ? "New subject" : "Confirm delete"
        }
        footer={<Button testID="academics-sheet-submit" title={sheet?.kind === "confirm" ? "Delete" : "Save"} variant={sheet?.kind === "confirm" ? "danger" : "primary"} loading={mut.isPending} onPress={() => mut.mutate()} />}
      >
        {sheet?.kind === "year" ? (
          <>
            <Field testID="year-name-input" label="Name" placeholder="2026-27" value={form.name} onChangeText={set("name")} />
            <Field testID="year-start-input" label="Start date (YYYY-MM-DD)" placeholder="2026-04-01" value={form.start} onChangeText={set("start")} />
            <Field testID="year-end-input" label="End date (YYYY-MM-DD)" placeholder="2027-03-31" value={form.end} onChangeText={set("end")} />
            <Row
              testID="year-current-toggle"
              title="Set as current session"
              subtitle="Dashboards and new admissions use the current session"
              right={<Badge label={form.current === "yes" ? "Yes" : "No"} tone={form.current === "yes" ? "success" : "neutral"} />}
              onPress={() => set("current")(form.current === "yes" ? "no" : "yes")}
              last
            />
          </>
        ) : sheet?.kind === "class" ? (
          <>
            <Field testID="class-name-input" label="Class name" placeholder="Class 7" value={form.name} onChangeText={set("name")} />
            <Field testID="class-order-input" label="Display order" keyboardType="number-pad" placeholder="7" value={form.order} onChangeText={set("order")} />
          </>
        ) : sheet?.kind === "section" ? (
          <>
            <Field testID="section-name-input" label="Section" placeholder="C" autoCapitalize="characters" value={form.name} onChangeText={set("name")} />
            <Field testID="section-capacity-input" label="Capacity" keyboardType="number-pad" value={form.capacity} onChangeText={set("capacity")} />
          </>
        ) : sheet?.kind === "subject" ? (
          <>
            <Field testID="subject-name-input" label="Subject name" placeholder="Environmental Studies" value={form.name} onChangeText={set("name")} />
            <Field testID="subject-code-input" label="Code" placeholder="EVS" autoCapitalize="characters" value={form.code} onChangeText={set("code")} />
          </>
        ) : sheet?.kind === "confirm" ? (
          <Txt variant="body">Delete {sheet.label}? Records that are still linked will block deletion to protect data integrity.</Txt>
        ) : null}
      </Sheet>
    </View>
  );
}
