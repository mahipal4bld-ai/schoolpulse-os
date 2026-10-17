import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Lifebuoy, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { CATEGORY_LABEL, STATUS_META, Ticket } from "@/src/components/helpdesk";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Insights = { open: number; overdue: number; unassigned: number; avg_first_response_hours: number | null; avg_resolution_hours: number | null; satisfaction: number | null; created: number };
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

function TicketCard({ t, onPress, staff }: { t: Ticket; onPress: () => void; staff: boolean }) {
  const { colors } = useTheme();
  const st = STATUS_META[t.status];
  return (
    <Pressable testID={`ticket-${t.id}`} onPress={onPress} accessibilityRole="button">
      <Card style={{ gap: spacing.xs, borderLeftWidth: 4, borderLeftColor: t.overdue ? colors.error : t.priority === "urgent" ? colors.warning : colors.border }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <Txt variant="caption" raw style={{ flex: 1 }}>{`#${t.number} · ${CATEGORY_LABEL[t.category]} · ${formatDateTime(t.last_activity_at)}`}</Txt>
          {t.overdue ? <Badge tone="error" label="Overdue" /> : null}
          <Badge tone={st.tone} label={staff ? st.label : st.parentLabel} />
        </View>
        <Txt variant="label" raw numberOfLines={1}>{t.subject}</Txt>
        <Txt variant="caption" raw numberOfLines={1}>{staff ? `${t.student_name} · ${t.guardian_name ?? ""}${t.assignee_name ? ` → ${t.assignee_name}` : " · Unassigned"}` : t.student_name}</Txt>
        {(staff ? t.unread_staff : t.unread_parent) ? <Txt variant="caption" color={colors.brandPrimary}>New reply</Txt> : null}
      </Card>
    </Pressable>
  );
}

function NewRequest({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { membership } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const kids = useQuery({ queryKey: ["parent-children", membership?.school_id], enabled: visible, queryFn: () => api<{ items: { id: string; first_name: string }[] }>("/parent/children") });
  const [f, setF] = useState({ child: "", category: "fees", subject: "", body: "", priority: "normal", cid: newId() });
  const child = f.child || kids.data?.items[0]?.id || "";
  const err = f.subject.trim().length < 4 ? "Add a short subject" : f.body.trim().length < 10 ? "Describe the request in a little more detail" : null;
  const save = useMutation({
    mutationFn: () => api<Ticket>("/helpdesk/tickets", { body: { student_id: child, category: f.category, subject: f.subject, body: f.body, priority: f.priority, client_id: f.cid } }),
    onSuccess: (t) => { qc.invalidateQueries({ queryKey: ["tickets"] }); setF({ child: "", category: "fees", subject: "", body: "", priority: "normal", cid: newId() }); onClose(); toast.show(`Request #${t.number} sent`); router.push(`/helpdesk/${t.id}`); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <Sheet visible={visible} onClose={onClose} title="New request" testID="ticket-new-sheet" footer={<Button testID="ticket-submit" title="Send request" disabled={!!err || !child} loading={save.isPending} onPress={() => save.mutate()} />}>
      {(kids.data?.items.length ?? 0) > 1 ? <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ticket-child" value={child} onChange={(c) => setF((p) => ({ ...p, child: c }))} options={kids.data!.items.map((k) => ({ value: k.id, label: k.first_name }))} /></View> : null}
      <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ticket-cat" value={f.category} onChange={(category) => setF((p) => ({ ...p, category }))} options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} /></View>
      <Field testID="ticket-subject" label="Subject" value={f.subject} onChangeText={(subject) => setF((p) => ({ ...p, subject }))} placeholder="e.g. Fee receipt not received" />
      <Field testID="ticket-body" label="Details" value={f.body} onChangeText={(body) => setF((p) => ({ ...p, body }))} multiline placeholder="What happened, and what do you need from the school?" />
      <Segmented testIDPrefix="ticket-priority" value={f.priority} onChange={(priority) => setF((p) => ({ ...p, priority }))} options={[{ value: "normal", label: "Normal" }, { value: "high", label: "Important" }]} />
      <Txt variant="caption">The school aims to reply within 48 hours (24 hours for important requests). Please do not share bank or card details here.</Txt>
    </Sheet>
  );
}

export default function HelpDesk() {
  const { membership, can } = useAuth();
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const parent = membership?.role === "parent";
  const manager = can("helpdesk.manage");
  const [view, setView] = useState(parent ? "all" : manager ? "active" : "mine");
  const [creating, setCreating] = useState(false);
  const q = useInfiniteQuery({
    queryKey: ["tickets", membership?.school_id, view], initialPageParam: "",
    queryFn: ({ pageParam }) => api<{ items: Ticket[]; next_cursor: string | null }>(`/helpdesk/tickets?view=${view}&limit=30${pageParam ? `&before=${pageParam}` : ""}`),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
    refetchInterval: 30000,
  });
  const ins = useQuery({ queryKey: ["helpdesk-insights", membership?.school_id], enabled: manager, queryFn: () => api<Insights>("/helpdesk/insights") });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const views = parent ? [{ value: "all", label: "All" }, { value: "active", label: "Open" }, { value: "done", label: "Resolved" }]
    : manager ? [{ value: "active", label: "Open" }, { value: "mine", label: "Assigned to me" }, { value: "unassigned", label: "Unassigned" }, { value: "overdue", label: "Overdue" }, { value: "done", label: "Resolved" }]
      : [{ value: "mine", label: "Open" }, { value: "done", label: "Resolved" }];
  const i = ins.data;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Help desk" subtitle={parent ? "Requests to the school office" : "Parent requests"} />
      <View style={{ paddingTop: spacing.sm }}><ChipRow testIDPrefix="ticket-view" value={view} onChange={(v) => setView(v === "mine" && !manager && !parent ? "mine" : v)} options={views} /></View>
      <FlatList
        testID="tickets-list"
        data={q.isLoading || q.isError ? [] : items}
        keyExtractor={(t) => t.id}
        onEndReached={() => q.hasNextPage && !q.isFetchingNextPage && q.fetchNextPage()}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); ins.refetch(); }} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + (parent ? 120 : spacing.xl), gap: spacing.md, flexGrow: 1 }}
        ListHeaderComponent={manager && i ? (
          <Card testID="helpdesk-insights" style={{ gap: spacing.xs }}>
            <Txt variant="heading" raw>{`${i.open} open · ${i.overdue} overdue · ${i.unassigned} unassigned`}</Txt>
            <Txt variant="caption" raw>{`Last 30 days: ${i.created} requests · first reply ${i.avg_first_response_hours ?? "–"}h avg · resolved in ${i.avg_resolution_hours ?? "–"}h avg · satisfaction ${i.satisfaction ?? "–"}/5`}</Txt>
          </Card>
        ) : null}
        ListEmptyComponent={q.isLoading ? <SkeletonList rows={3} /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
          <EmptyState testID="tickets-empty" icon={<Lifebuoy size={40} color={colors.muted} />} title={parent ? "No requests yet" : "Nothing here"} message={parent ? "Ask the school office about fees, transport, documents and more." : "Requests matching this view appear here."} />
        )}
        renderItem={({ item }) => <TicketCard t={item} staff={!parent} onPress={() => router.push(`/helpdesk/${item.id}`)} />}
      />
      {parent ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="ticket-new-button" title="New request" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setCreating(true)} />
        </View>
      ) : null}
      {parent ? <NewRequest visible={creating} onClose={() => setCreating(false)} /> : null}
    </View>
  );
}
