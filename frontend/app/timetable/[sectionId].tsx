import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { DaySchedule, DayTabs, Grid, Slot } from "@/src/components/timetable";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type EditGrid = Grid & { teacher_options?: { teacher_id: string; name: string; subject_ids: string[]; is_class_teacher: boolean }[]; subjects?: { id: string; name: string }[] };

export default function SectionTimetable() {
  const { sectionId } = useLocalSearchParams<{ sectionId: string }>();
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["timetable", membership?.school_id, sectionId];
  const q = useQuery({ queryKey: key, queryFn: () => api<EditGrid>(`/timetable/sections/${sectionId}`) });
  const [picked, setDay] = useState<number | null>(null);
  const [edit, setEdit] = useState<{ period: number; subject_id: string; teacher_id: string; room: string; existing: boolean } | null>(null);
  const t = q.data?.today ?? 1;
  const day = picked ?? (t >= 1 && t <= 6 ? t : 1);
  const done = (d: EditGrid, msg: string) => {
    qc.setQueryData(key, d);
    qc.invalidateQueries({ queryKey: ["my-timetable"] });
    setEdit(null);
    toast.show(msg);
  };
  const save = useMutation({
    mutationFn: () => api<EditGrid>(`/timetable/sections/${sectionId}/slots`, { method: "PUT", body: { day, period: edit!.period, subject_id: edit!.subject_id, teacher_id: edit!.teacher_id || null, room: edit!.room } }),
    onSuccess: (d) => done(d, "Period saved"),
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const clear = useMutation({
    mutationFn: () => api<EditGrid>(`/timetable/sections/${sectionId}/slots?day=${day}&period=${edit!.period}`, { method: "DELETE" }),
    onSuccess: (d) => done(d, "Period cleared"),
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const manage = can("academic.manage");
  const teachers = (q.data?.teacher_options ?? []).filter((t) => !edit?.subject_id || t.is_class_teacher || t.subject_ids.includes(edit.subject_id));
  const open = (period: number, s?: Slot) => setEdit({ period, subject_id: s?.subject_id ?? q.data?.subjects?.[0]?.id ?? "", teacher_id: s?.teacher_id ?? "", room: s?.room ?? "", existing: !!s });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Timetable" subtitle={q.data?.section} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}>
          <DayTabs grid={q.data!} day={day} onChange={setDay} />
          <DaySchedule grid={q.data!} day={day} show="teacher" onPress={manage ? open : undefined} />
          {manage ? <Txt variant="caption">Tap a period to assign subject, teacher and room. Teacher and room clashes are blocked.</Txt> : null}
        </ScrollView>
      )}
      <Sheet visible={!!edit} onClose={() => setEdit(null)} title={edit ? `Period ${edit.period}` : ""} testID="tt-slot-sheet" footer={
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {edit?.existing ? <Button style={{ flex: 1 }} variant="outline" testID="tt-slot-clear" title="Clear" loading={clear.isPending} onPress={() => clear.mutate()} /> : null}
          <Button style={{ flex: 1 }} testID="tt-slot-save" title="Save" loading={save.isPending} onPress={() => save.mutate()} />
        </View>
      }>
        {edit ? (
          <>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Subject</Txt>
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="tt-subject" value={edit.subject_id} onChange={(subject_id) => setEdit({ ...edit, subject_id, teacher_id: "" })} options={(q.data?.subjects ?? []).map((s) => ({ value: s.id, label: s.name }))} />
            </View>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Teacher</Txt>
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="tt-teacher" value={edit.teacher_id} onChange={(teacher_id) => setEdit({ ...edit, teacher_id })} options={[{ value: "", label: "None" }, ...teachers.map((t) => ({ value: t.teacher_id, label: t.name }))]} />
            </View>
            <Field testID="tt-room-input" label="Room (optional)" value={edit.room} onChangeText={(room) => setEdit({ ...edit, room })} placeholder="e.g. Lab 2" />
          </>
        ) : null}
      </Sheet>
    </View>
  );
}
