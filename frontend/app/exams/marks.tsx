import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { FlatList, Pressable, TextInput, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useToast } from "@/src/components/toast";
import { Badge, Button, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

type Sheet = { exam: string; status: string; subject: string; section: string; max_marks: number; pass_marks: number; entered: boolean; students: { id: string; name: string; roll_no?: number; marks: number | null; absent: boolean }[] };
type Entry = { text: string; absent: boolean };

export default function MarksEntry() {
  const { exam, section, subject } = useLocalSearchParams<{ exam: string; section: string; subject: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const path = `/exams/${exam}/marks?section_id=${section}&subject_id=${subject}`;
  const q = useQuery({ queryKey: ["exam-marks", exam, section, subject], queryFn: () => api<Sheet>(path) });
  const [edits, setVals] = useState<Record<string, Entry>>({});
  const vals: Record<string, Entry> = { ...Object.fromEntries((q.data?.students ?? []).map((s) => [s.id, { text: s.marks === null ? "" : String(s.marks), absent: s.absent }])), ...edits };
  const locked = q.data?.status !== "marks_open";
  const save = useMutation({
    mutationFn: () => api<Sheet>(path, { method: "PUT", body: { records: Object.entries(vals).map(([student_id, v]) => ({ student_id, absent: v.absent, marks: v.absent || v.text === "" ? null : Number(v.text) })) } }),
    onSuccess: (d) => {
      qc.setQueryData(["exam-marks", exam, section, subject], d);
      setVals({});
      qc.invalidateQueries({ queryKey: ["exam"] });
      qc.invalidateQueries({ queryKey: ["exams"] });
      toast.show("Marks saved");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const filled = Object.values(vals).filter((v) => v.absent || v.text !== "").length;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={q.data ? `${q.data.subject} · ${q.data.section}` : "Marks entry"} subtitle={q.data ? `${q.data.exam} · max ${q.data.max_marks}, pass ${q.data.pass_marks}` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="marks-list"
          data={q.data!.students}
          keyExtractor={(s) => s.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 160, gap: spacing.sm }}
          ListHeaderComponent={<View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm }}>{locked ? <Badge tone="warning" label="Locked · results published" /> : <Badge tone="brand" label={`${filled}/${q.data!.students.length} filled`} />}</View>}
          renderItem={({ item }) => {
            const v = vals[item.id] ?? { text: "", absent: false };
            const n = Number(v.text);
            const bad = v.text !== "" && (isNaN(n) || n < 0 || n > q.data!.max_marks);
            return (
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: bad ? colors.error : colors.border, padding: spacing.sm, paddingLeft: spacing.md, minHeight: 56 }}>
                <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{item.roll_no ? `${item.roll_no}. ` : ""}{item.name}</Txt>
                <Pressable testID={`marks-absent-${item.id}`} disabled={locked} onPress={() => setVals((x) => ({ ...x, [item.id]: { text: "", absent: !v.absent } }))} style={{ height: 40, paddingHorizontal: spacing.sm, borderRadius: radius.sm, justifyContent: "center", backgroundColor: v.absent ? colors.errorSoft : colors.surfaceSecondary }}>
                  <Txt variant="caption" raw color={v.absent ? colors.error : colors.onSurfaceTertiary}>AB</Txt>
                </Pressable>
                <TextInput
                  testID={`marks-input-${item.id}`}
                  editable={!locked && !v.absent}
                  value={v.absent ? "" : v.text}
                  onChangeText={(text) => setVals((x) => ({ ...x, [item.id]: { text: text.replace(/[^0-9.]/g, ""), absent: false } }))}
                  keyboardType="decimal-pad"
                  placeholder="—"
                  placeholderTextColor={colors.muted}
                  style={{ width: 64, height: 40, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, textAlign: "center", color: colors.onSurface, fontSize: 16 }}
                />
              </View>
            );
          }}
        />
      )}
      {q.data && !locked ? (
        <KeyboardStickyView offset={{ opened: insets.bottom }} style={{ position: "absolute", left: 0, right: 0, bottom: 0 }}>
          <View style={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
            <Button testID="marks-save-button" title={q.data.entered ? "Update marks" : "Save marks"} loading={save.isPending} onPress={() => save.mutate()} />
          </View>
        </KeyboardStickyView>
      ) : null}
    </View>
  );
}
