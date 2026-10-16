import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarX } from "phosphor-react-native";
import React, { useState } from "react";
import { FlatList, RefreshControl, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Leave, LeaveCard } from "@/src/components/leave-card";
import { Button, ChipRow, EmptyState, ErrorState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Filter = "pending" | "approved" | "rejected" | "all";

export default function LeaveApprovals() {
  const { membership, can } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("pending");
  const [deciding, setDeciding] = useState<{ lv: Leave; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const q = useQuery({
    queryKey: ["leave", membership?.school_id, filter],
    queryFn: () => api<{ items: Leave[]; pending: number }>(`/staff/leave${filter === "all" ? "" : `?status=${filter}`}`),
  });
  const decide = useMutation({
    mutationFn: () => api(`/staff/leave/${deciding!.lv.id}/decision`, { body: { approve: deciding!.approve, note: note || null } }),
    onSuccess: () => {
      toast.show(deciding!.approve ? "Leave approved" : "Leave rejected");
      setDeciding(null);
      setNote("");
      qc.invalidateQueries({ queryKey: ["leave"] });
      qc.invalidateQueries({ queryKey: ["staff-today"] });
      qc.invalidateQueries({ queryKey: ["staff-reg"] });
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  const approver = can("leave.approve");

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Leave requests" subtitle={q.data ? `${q.data.pending} awaiting decision` : undefined} />
      <ChipRow testIDPrefix="leave-filter" value={filter} onChange={setFilter} options={[{ value: "pending", label: "Pending" }, { value: "approved", label: "Approved" }, { value: "rejected", label: "Rejected" }, { value: "all", label: "All" }]} />
      {q.isLoading ? <SkeletonList /> : q.isError ? <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} /> : (
        <FlatList
          testID="leave-list"
          data={q.data!.items}
          keyExtractor={(x) => x.id}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md, flexGrow: 1 }}
          ListEmptyComponent={<EmptyState icon={<CalendarX size={40} color={colors.muted} />} title="No leave requests" message="Requests from teachers appear here." />}
          renderItem={({ item }) => (
            <LeaveCard
              lv={item}
              footer={approver && item.status === "pending" ? (
                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs }}>
                  <Button small style={{ flex: 1 }} variant="outline" title="Reject" testID={`leave-reject-${item.id}`} onPress={() => setDeciding({ lv: item, approve: false })} />
                  <Button small style={{ flex: 1 }} title="Approve" testID={`leave-approve-${item.id}`} onPress={() => setDeciding({ lv: item, approve: true })} />
                </View>
              ) : null}
            />
          )}
        />
      )}
      <Sheet
        visible={!!deciding}
        onClose={() => setDeciding(null)}
        testID="leave-decision-sheet"
        title={deciding?.approve ? "Approve leave" : "Reject leave"}
        footer={<Button testID="leave-decision-submit" title={deciding?.approve ? "Approve" : "Reject"} variant={deciding?.approve ? "primary" : "danger"} loading={decide.isPending} onPress={() => decide.mutate()} />}
      >
        {deciding ? <Txt variant="body" raw>{deciding.lv.teacher_name} · {deciding.lv.days} day(s) from {formatDate(deciding.lv.from_date)}</Txt> : null}
        <Field testID="leave-decision-note" label={deciding?.approve ? "Note (optional)" : "Reason for rejection"} value={note} onChangeText={setNote} placeholder={deciding?.approve ? "e.g. Approved, arrange substitute" : "e.g. Exam duty that week"} />
      </Sheet>
    </View>
  );
}
