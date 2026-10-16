import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import { Paperclip, X } from "phosphor-react-native";
import React, { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api";
import { Attachment, isoDay } from "@/src/components/homework";
import { useToast } from "@/src/components/toast";
import { Button, ChipRow, EmptyState, Field, Header, SkeletonList, Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";
import { uploadForm } from "@/src/utils/upload";

type Opt = { section_id: string; label: string; subjects: { id: string; name: string }[] };

export default function NewHomework() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const router = useRouter();
  const qc = useQueryClient();
  const opts = useQuery({ queryKey: ["homework-options"], queryFn: () => api<{ items: Opt[] }>("/homework/options") });
  const [section, setSection] = useState("");
  const [subject, setSubject] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [due, setDue] = useState(isoDay(1));
  const [files, setFiles] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!section && opts.data?.items.length) setSection(opts.data.items[0].section_id);
  }, [opts.data, section]);
  const current = opts.data?.items.find((o) => o.section_id === section);
  useEffect(() => {
    if (current && !current.subjects.some((s) => s.id === subject)) setSubject(current.subjects[0]?.id ?? "");
  }, [current, subject]);

  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ type: ["application/pdf", "image/jpeg", "image/png", "image/webp"], copyToCacheDirectory: true });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    setUploading(true);
    try {
      const up = await uploadForm<Attachment>("/homework/attachments", { uri: a.uri, name: a.name, type: a.mimeType || "application/pdf" });
      setFiles((f) => [...f, up]);
    } catch (e) {
      toast.show((e as Error).message, "error");
    } finally {
      setUploading(false);
    }
  };

  const save = useMutation({
    mutationFn: (publish: boolean) => api<{ id: string }>("/homework", { body: { section_id: section, subject_id: subject, title, description, due_date: due, attachments: files.map((f) => f.id), publish } }),
    onSuccess: (d, publish) => {
      qc.invalidateQueries({ queryKey: ["homework"] });
      toast.show(publish ? "Homework published to parents" : "Draft saved");
      router.replace(`/homework/${d.id}`);
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Header back title="New homework" />
      {opts.isLoading ? <SkeletonList rows={4} /> : !opts.data?.items.length ? (
        <EmptyState title="No classes assigned" message="You can create homework once a section is assigned to you." />
      ) : (
        <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 140, gap: spacing.lg }}>
          <View>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Section</Txt>
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="hw-section" value={section} onChange={setSection} options={opts.data.items.map((o) => ({ value: o.section_id, label: o.label }))} />
            </View>
          </View>
          <View>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Subject</Txt>
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="hw-subject" value={subject} onChange={setSubject} options={(current?.subjects ?? []).map((s) => ({ value: s.id, label: s.name }))} />
            </View>
          </View>
          <Field testID="hw-title-input" label="Title" value={title} onChangeText={setTitle} placeholder="e.g. Fractions worksheet" />
          <Field testID="hw-description-input" label="Instructions" value={description} onChangeText={setDescription} placeholder="e.g. Solve exercise 3.2, questions 1 to 10" multiline style={{ minHeight: 96, textAlignVertical: "top" }} />
          <View style={{ gap: spacing.sm }}>
            <Field testID="hw-due-input" label="Due date (YYYY-MM-DD)" value={due} onChangeText={setDue} autoCapitalize="none" />
            <View style={{ marginHorizontal: -spacing.lg }}>
              <ChipRow testIDPrefix="hw-due" value={due} onChange={setDue} options={[{ value: isoDay(1), label: "Tomorrow" }, { value: isoDay(2), label: "In 2 days" }, { value: isoDay(7), label: "Next week" }]} />
            </View>
          </View>
          <View style={{ gap: spacing.sm }}>
            {files.map((f) => (
              <View key={f.id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
                <Paperclip size={18} color={colors.brandPrimary} />
                <Txt variant="body" raw numberOfLines={1} style={{ flex: 1 }}>{f.name}</Txt>
                <Pressable testID={`hw-remove-file-${f.id}`} hitSlop={8} onPress={() => setFiles((x) => x.filter((y) => y.id !== f.id))} style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center" }}>
                  <X size={16} color={colors.muted} />
                </Pressable>
              </View>
            ))}
            {files.length < 5 ? <Button testID="hw-attach-button" variant="outline" title="Attach PDF or image" loading={uploading} icon={<Paperclip size={16} color={colors.onSurface} />} onPress={pick} /> : null}
          </View>
        </KeyboardAwareScrollView>
      )}
      {opts.data?.items.length ? (
        <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", gap: spacing.sm, padding: spacing.lg, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button style={{ flex: 1 }} variant="outline" testID="hw-save-draft" title="Save draft" disabled={uploading} loading={save.isPending && save.variables === false} onPress={() => save.mutate(false)} />
          <Button style={{ flex: 1 }} testID="hw-publish" title="Publish" disabled={uploading} loading={save.isPending && save.variables === true} onPress={() => save.mutate(true)} />
        </View>
      ) : null}
    </View>
  );
}
