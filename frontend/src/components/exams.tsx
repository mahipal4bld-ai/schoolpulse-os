import { FilePdf } from "phosphor-react-native";
import React, { useState } from "react";
import { View } from "react-native";

import { useToast } from "@/src/components/toast";
import { Button, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";
import { openSecureDownload } from "@/src/utils/download";

export type ExamT = {
  id: string;
  name: string;
  term: string;
  start_date: string;
  end_date: string;
  status: "marks_open" | "published";
  subjects: { subject_id: string; subject_name: string; max_marks: number; pass_marks: number }[];
  sheets: { section_id: string; section_label: string; subject_id: string; subject_name: string; entered: boolean }[];
  sections: { id: string; label: string }[];
  progress: { entered: number; total: number };
};
export type SubjectLine = { subject: string; max: number; marks: number | null; absent: boolean; grade: string | null; passed: boolean; entered: boolean };
export const STATUS_LABEL = { marks_open: "Marks entry open", published: "Results published" } as const;

export function SubjectLines({ lines }: { lines: SubjectLine[] }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: spacing.xs }}>
      {lines.map((l) => (
        <View key={l.subject} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 28 }}>
          <Txt variant="body" raw style={{ flex: 1 }} numberOfLines={1}>{l.subject}</Txt>
          <Txt variant="label" raw color={l.entered && !l.passed ? colors.error : colors.onSurface}>{l.absent ? "AB" : l.marks === null ? "—" : `${l.marks}/${l.max}`}</Txt>
          <Txt variant="caption" raw style={{ width: 28, textAlign: "right" }}>{l.grade ?? ""}</Txt>
        </View>
      ))}
    </View>
  );
}

export function ReportCardButton({ examId, studentId, testID }: { examId: string; studentId: string; testID: string }) {
  const { colors } = useTheme();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const base = `/exams/${examId}/report-card/${studentId}`;
  const open = () => {
    setBusy(true);
    openSecureDownload({ headerPath: `${base}.pdf`, grantPath: `${base}/download-grant`, filename: "report-card.pdf" })
      .catch((e: Error) => toast.show(e.message, "error"))
      .finally(() => setBusy(false));
  };
  return <Button small variant="outline" testID={testID} title="Report card (PDF)" loading={busy} icon={<FilePdf size={16} color={colors.onSurface} />} onPress={open} />;
}
