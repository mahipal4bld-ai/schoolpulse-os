import { useMutation, useQueryClient } from "@tanstack/react-query";
import React, { useState } from "react";
import { View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useToast } from "@/src/components/toast";
import { Badge, Button, Card, Field, Header, SectionTitle, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

const SAMPLE = `admission_no,first_name,last_name,gender,dob,class,section,guardian_name,guardian_phone,guardian_relation
NEW001,Aditi,Rao,female,2017-06-12,Class 2,A,Suresh Rao,9876501234,father`;

type Result = { rows: number; valid: number; created: number; dry_run: boolean; errors: { row: number; error: string }[] };

export default function ImportCsv() {
  const { membership } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState(SAMPLE);
  const [res, setRes] = useState<Result | null>(null);
  const run = useMutation({
    mutationFn: (dry: boolean) => api<Result>("/students/import", { body: { csv_text: text, dry_run: dry } }),
    onSuccess: (r) => {
      setRes(r);
      if (!r.dry_run) {
        qc.invalidateQueries({ queryKey: ["people", membership?.school_id] });
        qc.invalidateQueries({ queryKey: ["owner-dash", membership?.school_id] });
        toast.show(`${r.created} students imported`);
      }
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Import students" subtitle="CSV · validate first, then import" />
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.xl }}>
        <Card style={{ gap: spacing.md }}>
          <SectionTitle title="Format" />
          <Txt variant="caption">Columns: admission_no, first_name, last_name, gender (male/female/other), dob (YYYY-MM-DD), class (exact name in current session), section, guardian_name, guardian_phone (10 digits), guardian_relation.</Txt>
          <Field testID="csv-text-input" label="Paste CSV" multiline value={text} onChangeText={setText} autoCapitalize="none" autoCorrect={false} style={{ minHeight: 160, fontSize: 12 }} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <Button style={{ flex: 1 }} testID="csv-validate-button" variant="outline" title="Validate" loading={run.isPending && run.variables === true} onPress={() => run.mutate(true)} />
            <Button style={{ flex: 1 }} testID="csv-import-button" title="Import" disabled={!res || res.dry_run === false || res.errors.length > 0} loading={run.isPending && run.variables === false} onPress={() => run.mutate(false)} />
          </View>
        </Card>
        {res ? (
          <Card testID="csv-result-card" style={{ gap: spacing.md }}>
            <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
              <Badge label={`${res.rows} rows`} />
              <Badge label={`${res.valid} valid`} tone="success" />
              {res.errors.length ? <Badge label={`${res.errors.length} errors`} tone="error" /> : null}
              {!res.dry_run ? <Badge label={`${res.created} imported`} tone="brand" /> : null}
            </View>
            {res.errors.map((e) => (
              <Txt key={e.row} variant="caption" color={colors.error}>Row {e.row}: {e.error}</Txt>
            ))}
            {res.dry_run && !res.errors.length ? <Txt variant="caption">All rows are valid. Tap Import to create them.</Txt> : null}
          </Card>
        ) : null}
      </KeyboardAwareScrollView>
    </View>
  );
}
