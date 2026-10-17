import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import { PaperPlaneRight } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, TextInput, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Attachment, AttachmentList } from "@/src/components/homework";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, ErrorState, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";
import type { Conv } from "@/src/components/conv-types";

type Msg = { id: string; body: string; mine: boolean; sender_role: string; created_at: string; status: string; attachments: Attachment[] };
type Page = { conversation: Conv; items: Msg[]; next_cursor: string | null };
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

export default function Thread() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const teacher = membership?.role === "teacher";
  // School leaders only review escalated threads; they never post into a parent–teacher conversation.
  const readOnly = !teacher && membership?.role !== "parent";
  const key = ["thread", membership?.school_id, id];
  // Newest page polls every 5 s; older pages load via cursor.
  const q = useInfiniteQuery({
    queryKey: key,
    initialPageParam: "",
    queryFn: ({ pageParam }) => api<Page>(`/conversations/${id}/messages?limit=30${pageParam ? `&before=${pageParam}` : ""}`),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
    refetchInterval: 5000,
  });
  const tpl = useQuery({ queryKey: ["msg-templates"], enabled: teacher, queryFn: () => api<{ items: { id: string; title: string; body: string }[] }>("/messaging/templates") });
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (clientId: string) => api(`/conversations/${id}/messages`, { body: { body: text, client_id: clientId } }),
    onSuccess: () => { setText(""); setPending(null); qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["convs"] }); },
    onError: (e: Error) => toast.show(`${e.message} — tap send to retry`, "error"),  // retry reuses the same client id (idempotent)
  });
  const status = useMutation({
    mutationFn: (act: string) => api(`/conversations/${id}/status?act=${act}`, { method: "POST" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ["convs"] }); toast.show("Updated"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const conv = q.data?.pages[0]?.conversation;
  const msgs = q.data?.pages.flatMap((p) => p.items) ?? [];
  const onSend = () => {
    if (!text.trim()) return;
    const cid = pending ?? newId();
    setPending(cid);
    send.mutate(cid);
  };
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title={conv ? (teacher ? conv.guardian_name : conv.teacher_name) : "Conversation"} subtitle={conv ? `${conv.student_name} · ${conv.topic}` : undefined} />
      {teacher && conv ? (
        <View style={{ flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.surface }}>
          <Button small variant="outline" testID="conv-follow-up" title={conv.follow_up ? "Clear follow-up" : "Follow up"} onPress={() => status.mutate(conv.follow_up ? "clear_follow_up" : "follow_up")} />
          <Button small variant="outline" testID="conv-escalate" title="Escalate" onPress={() => status.mutate("escalate")} />
          <Button small variant="outline" testID="conv-close" title={conv.status === "closed" ? "Re-open" : "Close"} onPress={() => status.mutate(conv.status === "closed" ? "reopen" : "close")} />
        </View>
      ) : null}
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="thread-list"
          inverted
          data={msgs}
          keyExtractor={(m) => m.id}
          onEndReached={() => q.hasNextPage && !q.isFetchingNextPage && q.fetchNextPage()}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm }}
          renderItem={({ item }) => (
            <View testID={`msg-${item.id}`} style={{ alignSelf: item.mine ? "flex-end" : "flex-start", maxWidth: "82%", padding: spacing.md, borderRadius: radius.lg, backgroundColor: item.mine ? colors.brandPrimary : colors.surface, gap: 4 }}>
              <Txt variant="body" raw color={item.mine ? colors.onBrandPrimary : colors.onSurface}>{item.body}</Txt>
              <AttachmentList items={item.attachments} testIDPrefix="msg-file" />
              <Txt variant="caption" raw color={item.mine ? colors.onBrandPrimary : colors.onSurfaceTertiary}>{formatDateTime(item.created_at)}{item.mine ? ` · ${item.status === "read" ? "Read" : "Sent"}` : ""}</Txt>
            </View>
          )}
        />
      )}
      {readOnly ? (
        <View testID="msg-readonly-note" style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Txt variant="caption">You are viewing this escalated conversation. Replies come from the class teacher.</Txt>
        </View>
      ) : (
      <KeyboardStickyView offset={{ opened: insets.bottom }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: insets.bottom + spacing.sm, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.xs }}>
          {teacher && tpl.data?.items.length ? (
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="tpl" value="" onChange={(v) => setText(tpl.data!.items.find((t) => t.id === v)?.body ?? text)} options={tpl.data.items.map((t) => ({ value: t.id, label: t.title }))} />
            </View>
          ) : null}
          <View style={{ flexDirection: "row", alignItems: "flex-end", gap: spacing.sm }}>
            <TextInput testID="msg-input" value={text} onChangeText={(v) => { setText(v); setPending(null); }} placeholder="Write a message" placeholderTextColor={colors.muted} multiline maxLength={2000}
              style={{ flex: 1, minHeight: 44, maxHeight: 120, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.onSurface, fontSize: 16 }} />
            <Pressable testID="msg-send" onPress={onSend} disabled={send.isPending} style={{ width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary, opacity: send.isPending ? 0.6 : 1 }}>
              <PaperPlaneRight size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
        </View>
      </KeyboardStickyView>
      )}
    </View>
  );
}
