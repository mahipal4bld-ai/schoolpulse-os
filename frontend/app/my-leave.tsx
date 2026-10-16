import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, CalendarX } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, EmptyState, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";
import { Leave, LeaveCard } from "@/src/components/leave-card";

type LType = "casual" | "sick" | "earned" | "other";
const isoToday = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);

export default function MyLeave() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ type: "casual" as LType, from: isoToday(), to: isoToday(), reason: "" });
  const q = useQuery({ queryKey: ["my-leave", membership?.school_id], queryFn: () => api<{ items: Leave[]; approved_days_this_year: number }>("/staff/leave/mine") });
  const done = () => {
    qc.invalidateQueries({ queryKey: ["my-leave"] });
    qc.invalidateQueries({ queryKey: ["staff-me"] });
  };
  const apply = useMutation({
    mutationFn: () => api("/staff/leave", { body: { type: form.type, from_date: form.from, to_date: form.to, reason: form.reason } }),
    onSuccess: () => {
      toast.show("Leave request sent for approval");
      setOpen(false);
      setForm({ type: "casual", from: isoToday(), to: isoToday(), reason: "" });
      done();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api(`/staff/leave/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      toast.show("Request cancelled");
      done();
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="My leave" subtitle={q.data ? `${q.data.approved_days_this_year} approved days this year` : undefined} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="my-leave-list"
          data={q.data!.items}
          keyExtractor={(x) => x.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<CalendarX size={40} color={colors.muted} />} title="No leave requests yet" message="Apply for leave and your principal will be notified in the app." />}
          renderItem={({ item }) => (
            <LeaveCard lv={item} footer={item.status === "pending" ? <Button small variant="outline" title="Cancel request" testID={`leave-cancel-${item.id}`} loading={cancel.isPending && cancel.variables === item.id} onPress={() => cancel.mutate(item.id)} /> : null} />
          )}
        />
      )}
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
        <Button testID="apply-leave-button" title="Apply for leave" icon={<CalendarPlus size={18} color={colors.onBrandPrimary} />} onPress={() => setOpen(true)} />
      </View>
      <Sheet visible={open} onClose={() => setOpen(false)} title="Apply for leave" testID="apply-leave-sheet" footer={<Button testID="apply-leave-submit" title="Send request" loading={apply.isPending} onPress={() => apply.mutate()} />}>
        <View>
          <Txt variant="label" color={colors.onSurfaceTertiary}>Type</Txt>
          <View style={{ marginHorizontal: -spacing.lg }}>
            <ChipRow testIDPrefix="leave-type" value={form.type} onChange={(v) => setForm((f) => ({ ...f, type: v }))} options={[{ value: "casual", label: "Casual" }, { value: "sick", label: "Sick" }, { value: "earned", label: "Earned" }, { value: "other", label: "Other" }]} />
          </View>
        </View>
        <Field testID="leave-from-input" label="From (YYYY-MM-DD)" value={form.from} onChangeText={(v) => setForm((f) => ({ ...f, from: v }))} autoCapitalize="none" />
        <Field testID="leave-to-input" label="To (YYYY-MM-DD)" value={form.to} onChangeText={(v) => setForm((f) => ({ ...f, to: v }))} autoCapitalize="none" />
        <Field testID="leave-reason-input" label="Reason" value={form.reason} onChangeText={(v) => setForm((f) => ({ ...f, reason: v }))} placeholder="e.g. Medical appointment" multiline />
      </Sheet>
    </View>
  );
}
