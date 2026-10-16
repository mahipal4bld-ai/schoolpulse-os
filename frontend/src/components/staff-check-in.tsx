import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { CalendarBlank, Fingerprint } from "phosphor-react-native";
import React from "react";
import { View } from "react-native";
import * as Haptics from "expo-haptics";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, IconTile, Row, Txt } from "@/src/components/ui";
import { formatDateTime } from "@/src/format";
import { spacing, useTheme } from "@/src/theme";

type Me = { date: string; status: string | null; check_in_at: string | null; on_leave: boolean; pending_leave: number };

/** Teacher self check-in + entry to "My leave". Hidden if no staff profile is linked. */
export function StaffCheckIn() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const key = ["staff-me", membership?.school_id];
  const q = useQuery({ queryKey: key, queryFn: () => api<Me>("/staff/me/today"), retry: false });
  const m = useMutation({
    mutationFn: () => api<Me>("/staff/me/check-in", { method: "POST" }),
    onSuccess: (d) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      qc.setQueryData(key, d);
      toast.show(d.status === "late" ? "Checked in (late)" : "Checked in");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  if (!q.data) return null;
  const d = q.data;
  return (
    <Card testID="staff-checkin-card" style={{ gap: spacing.md }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <IconTile><Fingerprint size={20} color={colors.onBrandTertiary} /></IconTile>
        <View style={{ flex: 1 }}>
          <Txt variant="label">My attendance</Txt>
          <Txt variant="caption" testID="staff-checkin-detail">
            {d.on_leave ? "On approved leave today" : d.check_in_at ? `Checked in ${formatDateTime(d.check_in_at)}` : d.status ? `Marked ${d.status.replace("_", " ")} by office` : "Not checked in yet"}
          </Txt>
        </View>
        {d.status ? <Badge testID="staff-checkin-status" tone={d.status === "present" ? "success" : d.status === "on_leave" ? "brand" : d.status === "absent" ? "error" : "warning"} label={d.status.replace("_", " ")} /> : null}
      </View>
      {!d.status ? <Button testID="staff-checkin-button" title="Check in now" loading={m.isPending} onPress={() => m.mutate()} /> : null}
      <View style={{ marginHorizontal: -spacing.lg, marginBottom: -spacing.lg }}>
        <Row testID="open-my-leave" last icon={<IconTile><CalendarBlank size={18} color={colors.onBrandTertiary} /></IconTile>} title="My leave" subtitle={d.pending_leave ? `${d.pending_leave} awaiting approval` : "Apply and track leave requests"} onPress={() => router.push("/my-leave")} />
      </View>
    </Card>
  );
}
