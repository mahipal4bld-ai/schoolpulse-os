import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Notice, NoticeCard } from "@/src/components/notices";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, Card, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function NoticeDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const key = ["notice", membership?.school_id, id];
  const q = useQuery({ queryKey: key, queryFn: () => api<Notice>(`/notices/${id}`) });
  const [edit, setEdit] = useState<{ body: string; reason: string } | null>(null);
  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ["notices"] });
    qc.invalidateQueries({ queryKey: key });
    toast.show(msg);
  };
  const act = useMutation({ mutationFn: (a: string) => api<Notice>(`/notices/${id}/action?act=${a}`, { method: "POST" }), onSuccess: (n) => done(`Notice ${n.status}`), onError: (e: Error) => toast.show(e.message, "error") });
  const save = useMutation({
    mutationFn: () => api<Notice>(`/notices/${id}`, { method: "PATCH", body: { body: edit!.body, reason: edit!.reason || null } }),
    onSuccess: () => { setEdit(null); done("Notice updated"); },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const n = q.data;
  const pct = (a: number) => (n?.stats?.audience ? Math.round((100 * a) / n.stats.audience) : 0);
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Notice" subtitle={n?.status} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : n ? (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.lg }}>
          <NoticeCard n={n} />
          {n.stats ? (
            <Card testID="notice-stats" style={{ flexDirection: "row", gap: spacing.lg }}>
              <View><Txt variant="heading" raw>{n.stats.audience}</Txt><Txt variant="caption">Parents reached</Txt></View>
              <View><Txt variant="heading" raw testID="notice-read-count">{n.stats.read}</Txt><Txt variant="caption" raw>Read · {pct(n.stats.read)}%</Txt></View>
              {n.requires_ack ? <View><Txt variant="heading" raw testID="notice-ack-count">{n.stats.acknowledged}</Txt><Txt variant="caption" raw>Acknowledged · {pct(n.stats.acknowledged)}%</Txt></View> : null}
            </Card>
          ) : null}
          {n.revision_count ? <Txt variant="caption" raw>Edited {n.revision_count} time(s) · history kept in audit log</Txt> : null}
          <View style={{ gap: spacing.sm }}>
            {["draft", "review", "scheduled"].includes(n.status) ? <Button testID="notice-action-publish" title="Publish now" loading={act.isPending} onPress={() => act.mutate("publish")} /> : null}
            {n.status === "draft" ? <Button testID="notice-action-review" variant="outline" title="Send for review" onPress={() => act.mutate("submit_review")} /> : null}
            {!["archived", "cancelled"].includes(n.status) ? <Button testID="notice-action-edit" variant="outline" title="Edit message" onPress={() => setEdit({ body: n.body, reason: "" })} /> : null}
            {n.status === "published" ? <Button testID="notice-action-archive" variant="outline" title="Archive" onPress={() => act.mutate("archive")} /> : null}
            {!["archived", "cancelled"].includes(n.status) ? <Button testID="notice-action-cancel" variant="danger" title="Cancel notice" onPress={() => act.mutate("cancel")} /> : null}
          </View>
        </ScrollView>
      ) : null}
      <Sheet visible={!!edit} onClose={() => setEdit(null)} title="Edit notice" testID="notice-edit-sheet" footer={<Button testID="notice-edit-save" title="Save" loading={save.isPending} onPress={() => save.mutate()} />}>
        {edit ? (
          <>
            <Field testID="notice-edit-body" label="Message" value={edit.body} onChangeText={(body) => setEdit({ ...edit, body })} multiline style={{ minHeight: 100, textAlignVertical: "top" }} />
            {n?.status === "published" ? <Field testID="notice-edit-reason" label="Reason for change" value={edit.reason} onChangeText={(reason) => setEdit({ ...edit, reason })} placeholder="e.g. Venue changed" /> : null}
          </>
        ) : null}
      </Sheet>
    </View>
  );
}
