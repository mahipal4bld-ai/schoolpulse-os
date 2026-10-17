import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { Star } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, Switch, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { CATEGORY_LABEL, MOVE_LABEL, STAFF_MOVES, STATUS_META, Ticket, TicketStatus } from "@/src/components/helpdesk";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, ErrorState, Field, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

function StaffBar({ t, refresh }: { t: Ticket; refresh: () => void }) {
  const { membership } = useAuth();
  const toast = useToast();
  const manager = t.side === "manager";
  const [move, setMove] = useState<TicketStatus | null>(null);
  const [note, setNote] = useState("");
  const [triage, setTriage] = useState(false);
  const people = useQuery({ queryKey: ["helpdesk-assignees", membership?.school_id], enabled: triage, queryFn: () => api<{ items: { user_id: string; name: string; role: string }[] }>("/helpdesk/assignees") });
  const go = useMutation({ mutationFn: () => api(`/helpdesk/tickets/${t.id}/status`, { body: { status: move, note } }), onSuccess: () => { setMove(null); setNote(""); refresh(); toast.show("Request updated"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const tri = useMutation({ mutationFn: (b: object) => api(`/helpdesk/tickets/${t.id}/triage`, { body: b }), onSuccess: () => { refresh(); toast.show("Request updated"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const moves = (STAFF_MOVES[t.status] ?? []).filter((m) => manager || m !== "closed");
  const needsNote = move === "waiting_on_parent" || move === "resolved";
  return (
    <>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
        {moves.map((m) => <Button key={m} small variant={m === "resolved" ? "primary" : "outline"} testID={`ticket-move-${m}`} title={MOVE_LABEL[m]} onPress={() => setMove(m)} />)}
        {manager && t.status !== "closed" ? <Button small variant="outline" testID="ticket-triage" title="Assign / priority" onPress={() => setTriage(true)} /> : null}
      </View>
      <Sheet visible={!!move} onClose={() => setMove(null)} title={move ? MOVE_LABEL[move] : ""} testID="ticket-move-sheet" footer={<Button testID="ticket-move-confirm" title="Confirm" disabled={needsNote && !note.trim()} loading={go.isPending} onPress={() => go.mutate()} />}>
        <Field testID="ticket-move-note" label={needsNote ? "Message to the parent" : "Note (optional, shown to the parent)"} value={note} onChangeText={setNote} multiline placeholder={move === "waiting_on_parent" ? "What do you need from the parent?" : "How was this resolved?"} />
      </Sheet>
      <Sheet visible={triage} onClose={() => setTriage(false)} title="Assign / priority" testID="ticket-triage-sheet">
        <Txt variant="label">Priority</Txt>
        <Segmented testIDPrefix="ticket-tri-priority" value={t.priority} onChange={(priority) => tri.mutate({ priority })} options={[{ value: "normal", label: "Normal" }, { value: "high", label: "High" }, { value: "urgent", label: "Urgent" }]} />
        <Txt variant="label">Category</Txt>
        <View style={{ marginHorizontal: -spacing.lg }}><ChipRow testIDPrefix="ticket-tri-cat" value={t.category} onChange={(category) => tri.mutate({ category })} options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} /></View>
        <Txt variant="label">Assign to</Txt>
        {people.isLoading ? <SkeletonList rows={2} /> : (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {(people.data?.items ?? []).map((p) => <Button key={p.user_id} small variant={p.user_id === t.assignee_user_id ? "primary" : "outline"} testID={`ticket-assign-${p.user_id}`} title={`${p.name} · ${p.role.replace("_", " ")}`} onPress={() => tri.mutate({ assignee_user_id: p.user_id })} />)}
          </View>
        )}
      </Sheet>
    </>
  );
}

function ParentBar({ t, refresh }: { t: Ticket; refresh: () => void }) {
  const toast = useToast();
  const { colors } = useTheme();
  const [reopen, setReopen] = useState(false);
  const [note, setNote] = useState("");
  const [score, setScore] = useState(0);
  const mv = useMutation({ mutationFn: (b: { status: string; note: string }) => api(`/helpdesk/tickets/${t.id}/status`, { body: b }), onSuccess: () => { setReopen(false); setNote(""); refresh(); toast.show("Request updated"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const rate = useMutation({ mutationFn: () => api(`/helpdesk/tickets/${t.id}/rate`, { body: { score } }), onSuccess: () => { refresh(); toast.show("Thanks for your feedback"); }, onError: (e: Error) => toast.show(e.message, "error") });
  const done = t.status === "resolved" || t.status === "closed";
  return (
    <>
      {done && !t.rating ? (
        <Card style={{ gap: spacing.sm }} testID="ticket-rate-card">
          <Txt variant="label">How did the school handle this?</Txt>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Pressable key={n} testID={`ticket-star-${n}`} accessibilityLabel={`${n} stars`} onPress={() => setScore(n)} style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}>
                <Star size={28} weight={n <= score ? "fill" : "regular"} color={n <= score ? colors.warning : colors.muted} />
              </Pressable>
            ))}
          </View>
          <Button small testID="ticket-rate-submit" title="Send rating" disabled={!score} loading={rate.isPending} onPress={() => rate.mutate()} />
        </Card>
      ) : t.rating ? <Txt variant="caption" raw testID="ticket-rated">{`You rated this ${t.rating.score}/5`}</Txt> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
        {t.status === "resolved" && t.can_reopen ? <Button small variant="outline" testID="ticket-reopen" title="Still not sorted" onPress={() => setReopen(true)} /> : null}
        {t.status === "resolved" ? <Button small testID="ticket-close" title="Close request" onPress={() => mv.mutate({ status: "closed", note: "" })} /> : null}
        {t.status === "open" || t.status === "assigned" ? <Button small variant="outline" testID="ticket-withdraw" title="Withdraw request" onPress={() => mv.mutate({ status: "closed", note: "Withdrawn by parent" })} /> : null}
      </View>
      <Sheet visible={reopen} onClose={() => setReopen(false)} title="Reopen request" testID="ticket-reopen-sheet" footer={<Button testID="ticket-reopen-confirm" title="Reopen" disabled={!note.trim()} loading={mv.isPending} onPress={() => mv.mutate({ status: "in_progress", note })} />}>
        <Field testID="ticket-reopen-note" label="What is still unresolved?" value={note} onChangeText={setNote} multiline />
      </Sheet>
    </>
  );
}

export default function TicketScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["ticket", membership?.school_id, id];
  const q = useQuery({ queryKey: key, refetchInterval: 15000, queryFn: () => api<Ticket>(`/helpdesk/tickets/${id}`) });
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [cid, setCid] = useState(newId);
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["tickets"] }); qc.invalidateQueries({ queryKey: ["helpdesk-insights"] }); };
  const send = useMutation({
    mutationFn: () => api(`/helpdesk/tickets/${id}/messages`, { body: { body: text, internal, client_id: cid } }),
    onSuccess: () => { setText(""); setInternal(false); setCid(newId()); refresh(); },
    onError: (e: Error) => toast.show(e.message, "error"),  // keep cid: a retry of the same text is deduplicated server-side
  });
  const t = q.data;
  const staff = t?.side !== "parent";
  const st = t ? STATUS_META[t.status] : null;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={t ? `#${t.number} ${t.subject}` : "Request"} subtitle={t ? `${CATEGORY_LABEL[t.category]} · ${t.student_name}${staff && t.guardian_name ? ` · ${t.guardian_name}` : ""}` : undefined}
        right={st ? <Badge testID="ticket-status" tone={st.tone} label={staff ? st.label : st.parentLabel} /> : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <>
          <FlatList
            testID="ticket-thread"
            data={t!.messages ?? []}
            keyExtractor={(m) => m.id}
            contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }}
            ListHeaderComponent={
              <View style={{ gap: spacing.md }}>
                <Card style={{ gap: spacing.xs }}>
                  <Txt variant="caption" raw>{`${formatDateTime(t!.created_at)}${staff ? ` · ${t!.priority} priority${t!.assignee_name ? ` · ${t!.assignee_name}` : " · Unassigned"}${t!.overdue ? " · OVERDUE" : ""}` : ""}`}</Txt>
                  <Txt variant="body" raw>{t!.body}</Txt>
                </Card>
                {staff ? <StaffBar t={t!} refresh={refresh} /> : <ParentBar t={t!} refresh={refresh} />}
              </View>
            }
            renderItem={({ item: m }) => (
              <View testID={`ticket-msg-${m.id}`} style={{ alignSelf: m.mine ? "flex-end" : "flex-start", maxWidth: "85%", padding: spacing.md, borderRadius: radius.lg, gap: 2,
                backgroundColor: m.internal ? colors.surfaceTertiary : m.mine ? colors.brandPrimary : colors.surface, borderWidth: m.internal ? 1 : 0, borderColor: colors.warning }}>
                <Txt variant="caption" raw color={m.mine && !m.internal ? colors.onBrandPrimary : colors.onSurfaceTertiary}>{`${m.internal ? "Internal note · " : ""}${m.author_name} · ${formatDateTime(m.created_at)}`}</Txt>
                <Txt variant="body" raw color={m.mine && !m.internal ? colors.onBrandPrimary : colors.onSurface}>{m.body}</Txt>
              </View>
            )}
          />
          {t!.status !== "closed" ? (
            <KeyboardStickyView offset={{ opened: insets.bottom }}>
              <View style={{ padding: spacing.md, paddingBottom: insets.bottom + spacing.md, gap: spacing.sm, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
                {staff ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                    <Switch testID="ticket-internal-switch" value={internal} onValueChange={setInternal} />
                    <Txt variant="caption">{internal ? "Internal note — never shown to the parent" : "Reply visible to the parent"}</Txt>
                  </View>
                ) : null}
                <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
                  <View style={{ flex: 1 }}><Field testID="ticket-reply-input" label="" value={text} onChangeText={setText} multiline placeholder={internal ? "Add an internal note" : "Write a reply"} /></View>
                  <Button testID="ticket-reply-send" title="Send" disabled={!text.trim()} loading={send.isPending} onPress={() => send.mutate()} />
                </View>
              </View>
            </KeyboardStickyView>
          ) : <Txt variant="caption" style={{ textAlign: "center", padding: spacing.lg }}>This request is closed. Raise a new request if you need more help.</Txt>}
        </>
      )}
    </View>
  );
}
