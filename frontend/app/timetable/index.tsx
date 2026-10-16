import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Clock, Table } from "phosphor-react-native";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ErrorState, Field, Header, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

type Opt = { section_id: string; label: string };
type Settings = { periods: { no: number; start: string; end: string }[] };

export default function TimetableHome() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const sid = membership?.school_id;
  const secs = useQuery({ queryKey: ["homework-options"], queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const st = useQuery({ queryKey: ["tt-settings", sid], queryFn: () => api<Settings>("/timetable/settings") });
  const conflicts = useQuery({ queryKey: ["tt-conflicts", sid], enabled: can("academic.manage"), queryFn: () => api<{ items: { teacher_name: string; day: string; period: number; sections: string[] }[] }>("/timetable/conflicts") });
  const [text, setText] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api<Settings>("/timetable/settings", { method: "PUT", body: { periods: text!.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [start, end] = l.split("-").map((x) => x.trim()); return { start, end }; }) } }),
    onSuccess: (d) => {
      qc.setQueryData(["tt-settings", sid], d);
      qc.invalidateQueries({ queryKey: ["timetable"] });
      setText(null);
      toast.show("Bell schedule saved");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Timetable" />
      {secs.isLoading || st.isLoading ? <SkeletonList /> : secs.isError ? <ErrorState message={(secs.error as Error).message} onRetry={() => secs.refetch()} /> : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
          {conflicts.data?.items.length ? (
            <Card testID="tt-conflicts-card" style={{ gap: spacing.xs }}>
              <Badge tone="error" label={`${conflicts.data.items.length} teacher clash(es)`} />
              {conflicts.data.items.map((c, i) => <Txt key={i} variant="caption" raw>{c.teacher_name} · {c.day} P{c.period}: {c.sections.join(", ")}</Txt>)}
            </Card>
          ) : null}
          <View>
            <SectionTitle title="Bell schedule" action={can("academic.manage") ? <Button small variant="ghost" title="Edit" testID="tt-edit-bells" onPress={() => setText(st.data!.periods.map((p) => `${p.start}-${p.end}`).join("\n"))} /> : undefined} />
            <Card testID="tt-bells-card" style={{ gap: spacing.xs }}>
              {st.data?.periods.map((p) => (
                <View key={p.no} style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                  <Clock size={14} color={colors.muted} />
                  <Txt variant="body" raw>Period {p.no}</Txt>
                  <View style={{ flex: 1 }} />
                  <Txt variant="caption" raw>{p.start} – {p.end}</Txt>
                </View>
              ))}
            </Card>
          </View>
          <View>
            <SectionTitle title="Class timetables" />
            <Card style={{ paddingVertical: 0 }}>
              {secs.data!.items.map((o, i) => (
                <Row key={o.section_id} testID={`tt-section-${o.section_id}`} last={i === secs.data!.items.length - 1} icon={<IconTile><Table size={18} color={colors.onBrandTertiary} /></IconTile>} title={o.label} onPress={() => router.push(`/timetable/${o.section_id}`)} />
              ))}
            </Card>
          </View>
        </ScrollView>
      )}
      <Sheet visible={text !== null} onClose={() => setText(null)} title="Edit bell schedule" testID="tt-bells-sheet" footer={<Button testID="tt-bells-save" title="Save" loading={save.isPending} onPress={() => save.mutate()} />}>
        <Txt variant="caption">One period per line as HH:MM-HH:MM, in order. Removing periods clears their timetable slots.</Txt>
        <Field testID="tt-bells-input" label="Periods" value={text ?? ""} onChangeText={setText} multiline autoCapitalize="none" style={{ minHeight: 180, textAlignVertical: "top" }} />
      </Sheet>
    </View>
  );
}
