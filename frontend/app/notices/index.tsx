import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Megaphone, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, Switch, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Notice, PRIORITY_TONE } from "@/src/components/notices";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Opt = { section_id: string; label: string };
type Filter = "all" | "published" | "scheduled" | "draft" | "review";
const CATS = ["general", "circular", "academic", "holiday", "exam", "event", "emergency"] as const;

export default function NoticesAdmin() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const q = useQuery({ queryKey: ["notices", membership?.school_id, filter], queryFn: () => api<{ items: Notice[] }>(`/notices${filter === "all" ? "" : `?status=${filter}`}`) });
  const secs = useQuery({ queryKey: ["homework-options"], queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const blank = { title: "", body: "", category: "general" as (typeof CATS)[number], priority: "normal" as Notice["priority"], scope: "school" as "school" | "sections", sections: [] as string[], publishAt: "", ack: false };
  const [f, setF] = useState<typeof blank | null>(null);
  const save = useMutation({
    mutationFn: (action: "draft" | "publish") => api<Notice>("/notices", { body: { title: f!.title, body: f!.body, category: f!.category, priority: f!.priority, requires_ack: f!.ack || f!.priority !== "normal", audience: { scope: f!.scope, section_ids: f!.scope === "sections" ? f!.sections : [] }, publish_at: f!.publishAt ? f!.publishAt.replace(" ", "T") : null, action } }),
    onSuccess: (n) => {
      qc.invalidateQueries({ queryKey: ["notices"] });
      setF(null);
      toast.show(n.status === "scheduled" ? "Notice scheduled" : n.status === "published" ? "Notice published" : "Draft saved");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Notices" subtitle="Announcements and circulars" />
      <ChipRow testIDPrefix="notice-filter" value={filter} onChange={setFilter} options={[{ value: "all", label: "All" }, { value: "published", label: "Published" }, { value: "scheduled", label: "Scheduled" }, { value: "review", label: "In review" }, { value: "draft", label: "Drafts" }]} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="notices-admin-list"
          data={q.data!.items}
          keyExtractor={(n) => n.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<Megaphone size={40} color={colors.muted} />} title="No notices yet" message="Publish announcements to parents by class or section." />}
          renderItem={({ item }) => (
            <Pressable testID={`notice-card-${item.id}`} onPress={() => router.push(`/notices/${item.id}`)}>
              <Card style={{ gap: spacing.xs }}>
                <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                  <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{item.title}</Txt>
                  <Badge tone={PRIORITY_TONE[item.priority]} label={item.priority} />
                </View>
                <Txt variant="caption" raw>{item.status}{item.published_at ? ` · ${formatDateTime(item.published_at)}` : item.publish_at ? ` · ${formatDateTime(item.publish_at)}` : ""}</Txt>
              </Card>
            </Pressable>
          )}
        />
      )}
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Button testID="new-notice-button" title="New notice" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setF(blank)} />
      </View>
      <Sheet visible={!!f} onClose={() => setF(null)} title="New notice" testID="notice-sheet" footer={
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <Button style={{ flex: 1 }} variant="outline" testID="notice-save-draft" title="Save draft" loading={save.isPending && save.variables === "draft"} onPress={() => save.mutate("draft")} />
          <Button style={{ flex: 1 }} testID="notice-publish" title={f?.publishAt ? "Schedule" : "Publish"} loading={save.isPending && save.variables === "publish"} onPress={() => save.mutate("publish")} />
        </View>
      }>
        {f ? (
          <>
            <Field testID="notice-title-input" label="Title" value={f.title} onChangeText={(title) => setF({ ...f, title })} placeholder="e.g. Annual sports day on Friday" />
            <Field testID="notice-body-input" label="Message" value={f.body} onChangeText={(body) => setF({ ...f, body })} multiline style={{ minHeight: 100, textAlignVertical: "top" }} placeholder="Write the announcement for parents" />
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="notice-cat" value={f.category} onChange={(category) => setF({ ...f, category })} options={CATS.map((c) => ({ value: c, label: c[0].toUpperCase() + c.slice(1) }))} />
            </View>
            <Segmented testIDPrefix="notice-priority" value={f.priority} onChange={(priority) => setF({ ...f, priority })} options={[{ value: "normal", label: "Normal" }, { value: "important", label: "Important" }, { value: "urgent", label: "Urgent" }]} />
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Txt variant="body">Ask parents to acknowledge</Txt>
              <Switch testID="notice-ack-switch" value={f.ack || f.priority !== "normal"} onValueChange={(ack) => setF({ ...f, ack })} />
            </View>
            <Segmented testIDPrefix="notice-scope" value={f.scope} onChange={(scope) => setF({ ...f, scope })} options={[{ value: "school", label: "Whole school" }, { value: "sections", label: "Sections" }]} />
            {f.scope === "sections" ? (
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                {(secs.data?.items ?? []).map((s) => {
                  const on = f.sections.includes(s.section_id);
                  return <Button key={s.section_id} small variant={on ? "primary" : "outline"} testID={`notice-sec-${s.section_id}`} title={s.label} onPress={() => setF({ ...f, sections: on ? f.sections.filter((x) => x !== s.section_id) : [...f.sections, s.section_id] })} />;
                })}
              </View>
            ) : null}
            <Field testID="notice-schedule-input" label="Schedule (optional, IST: YYYY-MM-DD HH:MM)" value={f.publishAt} onChangeText={(publishAt) => setF({ ...f, publishAt })} autoCapitalize="none" placeholder="Leave empty to publish now" />
          </>
        ) : null}
      </Sheet>
    </View>
  );
}
