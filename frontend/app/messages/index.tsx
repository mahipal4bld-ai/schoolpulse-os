import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ChatsCircle, Plus } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, ChipRow, EmptyState, ErrorState, Field, Header, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";
import type { Conv } from "@/src/components/conv-types";

const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

export default function Conversations() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const role = membership?.role;
  const leader = role === "owner" || role === "principal" || role === "school_admin";
  const [box, setBox] = useState<"mine" | "escalated">(leader ? "escalated" : "mine");
  const q = useQuery({ queryKey: ["convs", membership?.school_id, box], queryFn: () => api<{ items: Conv[] }>(`/conversations?box=${box}`), refetchInterval: 15000 });
  const kids = useQuery({ queryKey: ["parent-children", membership?.school_id], enabled: role === "parent", queryFn: () => api<{ items: { id: string; first_name: string }[] }>("/parent/children") });
  const [f, setF] = useState<{ student: string; teacher: string; topic: string; body: string } | null>(null);
  const tq = useQuery({ queryKey: ["msg-teachers", f?.student], enabled: !!f?.student, queryFn: () => api<{ items: { teacher_id: string; name: string; role: string; availability: string }[] }>(`/messaging/teachers?student_id=${f!.student}`) });
  const start = useMutation({
    mutationFn: () => api<Conv>("/conversations", { body: { student_id: f!.student, teacher_id: f!.teacher, topic: f!.topic, body: f!.body, client_id: newId() } }),
    onSuccess: (c) => { setF(null); qc.invalidateQueries({ queryKey: ["convs"] }); router.push(`/messages/${c.id}`); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Messages" subtitle={leader ? "Escalated conversations" : "Parent–teacher conversations"} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="conversations-list"
          data={q.data!.items}
          keyExtractor={(c) => c.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.sm, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<ChatsCircle size={40} color={colors.muted} />} title="No conversations" message={role === "parent" ? "Message your child's teachers here." : "Conversations appear here."} />}
          renderItem={({ item }) => (
            <Pressable testID={`conv-${item.id}`} onPress={() => router.push(`/messages/${item.id}`)}>
              <Card style={{ gap: 2 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Txt variant="label" raw style={{ flex: 1 }} numberOfLines={1}>{role === "parent" ? item.teacher_name : `${item.guardian_name} · ${item.student_name}`}</Txt>
                  {item.unread ? <Badge testID={`conv-unread-${item.id}`} tone="brand" label={String(item.unread)} /> : null}
                  {item.follow_up ? <Badge tone="warning" label="Follow up" /> : null}
                  {item.status !== "open" ? <Badge tone="neutral" label={item.status} /> : null}
                </View>
                <Txt variant="caption" raw numberOfLines={1}>{item.topic}{role === "parent" ? ` · ${item.student_name}` : ""}</Txt>
                <Txt variant="caption" raw numberOfLines={1}>{item.last_preview ?? ""} · {formatDateTime(item.last_message_at)}</Txt>
              </Card>
            </Pressable>
          )}
        />
      )}
      {role === "parent" ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="new-conversation-button" title="Message a teacher" icon={<Plus size={18} color={colors.onBrandPrimary} />} onPress={() => setF({ student: kids.data?.items[0]?.id ?? "", teacher: "", topic: "", body: "" })} />
        </View>
      ) : null}
      {leader ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface }}>
          <Segmented testIDPrefix="conv-box" value={box} onChange={setBox} options={[{ value: "escalated", label: "Escalated" }]} />
        </View>
      ) : null}
      <Sheet visible={!!f} onClose={() => setF(null)} title="Message a teacher" testID="new-conv-sheet" footer={<Button testID="new-conv-send" title="Send" loading={start.isPending} disabled={!f?.teacher} onPress={() => start.mutate()} />}>
        {f ? (
          <>
            {(kids.data?.items.length ?? 0) > 1 ? (
              <View style={{ marginHorizontal: -spacing.lg }}>
                <ChipRow testIDPrefix="conv-child" value={f.student} onChange={(student) => setF({ ...f, student, teacher: "" })} options={kids.data!.items.map((k) => ({ value: k.id, label: k.first_name }))} />
              </View>
            ) : null}
            <Txt variant="label" color={colors.onSurfaceTertiary}>Teacher</Txt>
            <View style={{ gap: spacing.xs }}>
              {(tq.data?.items ?? []).map((t) => (
                <Button key={t.teacher_id} small variant={f.teacher === t.teacher_id ? "primary" : "outline"} testID={`conv-teacher-${t.teacher_id}`} title={`${t.name} · ${t.role}${t.availability !== "available" ? ` (${t.availability})` : ""}`} onPress={() => setF({ ...f, teacher: t.teacher_id })} />
              ))}
            </View>
            <Field testID="conv-topic-input" label="Topic" value={f.topic} onChangeText={(topic) => setF({ ...f, topic })} placeholder="e.g. Homework doubt" />
            <Field testID="conv-body-input" label="Message" value={f.body} onChangeText={(body) => setF({ ...f, body })} multiline style={{ minHeight: 80, textAlignVertical: "top" }} />
            <Txt variant="caption">Teachers usually reply during school hours (7 am – 8 pm).</Txt>
          </>
        ) : null}
      </Sheet>
    </View>
  );
}
