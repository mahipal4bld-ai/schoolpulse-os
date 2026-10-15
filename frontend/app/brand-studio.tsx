import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { Check, ImageSquare, UploadSimple } from "phosphor-react-native";
import React, { useState } from "react";
import { Linking, Platform, Pressable, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, fileUrl, uploadImage } from "@/src/api";
import { useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { Sheet } from "@/src/components/sheet";
import { useToast } from "@/src/components/toast";
import { Button, Card, Field, Header, SectionTitle, Segmented, Txt } from "@/src/components/ui";
import { radius, readableOn, spacing, tint, useTheme } from "@/src/theme";
import type { Brand } from "@/src/types";

const PRESETS = ["#0A192F", "#1E3A8A", "#0F766E", "#14532D", "#9A3412", "#7F1D1D", "#581C87", "#334155"];
const ACCENTS = ["#0D9488", "#D97706", "#65A30D", "#2563EB", "#DB2777", "#CA8A04", "#0891B2", "#EA580C"];
const HEX = /^#[0-9A-Fa-f]{6}$/;

function Swatches({ values, value, onPick, prefix }: { values: string[]; value: string; onPick: (v: string) => void; prefix: string }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
      {values.map((c) => (
        <Pressable key={c} testID={`${prefix}-swatch-${c.slice(1)}`} onPress={() => onPick(c)} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: c, alignItems: "center", justifyContent: "center" }}>
          {value.toUpperCase() === c ? <Check size={18} color={readableOn(c)} weight="bold" /> : null}
        </Pressable>
      ))}
    </View>
  );
}

export default function BrandStudio() {
  const { membership, refresh } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const qc = useQueryClient();
  const school = membership!.school;
  const [b, setB] = useState<Brand>({ ...school.brand });
  const [tagline, setTagline] = useState(school.tagline ?? "");
  const [uploading, setUploading] = useState<"" | "logo" | "banner">("");
  const [perm, setPerm] = useState<null | { target: "logo" | "banner"; blocked: boolean }>(null);
  const validHex = HEX.test(b.primary) && HEX.test(b.secondary);

  const pickNow = async (target: "logo" | "banner") => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], allowsEditing: true, aspect: target === "logo" ? [1, 1] : [16, 9], quality: 0.7 });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setUploading(target);
    try {
      const up = await uploadImage(a.uri, target, a.mimeType || "image/jpeg");
      setB((x) => ({ ...x, [target === "logo" ? "logo_file_id" : "banner_file_id"]: up.id }));
      toast.show(`${target === "logo" ? "Logo" : "Banner"} uploaded — save to apply`, "info");
    } catch (e: any) {
      toast.show(e.message, "error");
    } finally {
      setUploading("");
    }
  };

  const pick = async (target: "logo" | "banner") => {
    if (Platform.OS === "web") return pickNow(target);
    const p = await ImagePicker.getMediaLibraryPermissionsAsync();
    if (p.granted) return pickNow(target);
    setPerm({ target, blocked: !p.canAskAgain });
  };

  const save = useMutation({
    mutationFn: async () => {
      await api("/school/brand", {
        method: "PATCH",
        body: {
          primary: b.primary,
          secondary: b.secondary,
          monogram: b.monogram,
          logo_style: b.logo_style,
          welcome_message: b.welcome_message,
          ...(b.logo_file_id ? { logo_file_id: b.logo_file_id } : { clear_logo: true }),
          ...(b.banner_file_id ? { banner_file_id: b.banner_file_id } : { clear_banner: true }),
        },
      });
      if (tagline !== (school.tagline ?? "")) await api("/school/settings", { method: "PATCH", body: { tagline } });
      await refresh();
    },
    onSuccess: () => {
      qc.invalidateQueries();
      toast.show("Brand saved. Your school app now uses it.");
    },
    onError: (e: Error) => toast.show(e.message, "error"),
  });

  const pv = validHex ? b.primary : school.brand.primary;
  const sv = validHex ? b.secondary : school.brand.secondary;
  const banner = fileUrl(b.banner_file_id);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <Header back title="Brand Studio" subtitle={school.name} />
      <KeyboardAwareScrollView bottomOffset={96} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 120, gap: spacing.xl }}>
        <View>
          <SectionTitle title="Live preview" />
          <View testID="brand-preview-card" style={{ borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg }}>
              <SchoolLogo brand={{ ...b, primary: pv, secondary: sv }} size={44} />
              <View style={{ flex: 1 }}>
                <Txt variant="heading">{school.name}</Txt>
                <Txt variant="caption">{tagline || "Your tagline"}</Txt>
              </View>
            </View>
            <View style={{ backgroundColor: pv, margin: spacing.lg, marginTop: 0, borderRadius: radius.md, overflow: "hidden" }}>
              {banner ? <Image source={{ uri: banner }} style={{ position: "absolute", width: "100%", height: "100%", opacity: 0.35 }} contentFit="cover" /> : null}
              <View style={{ padding: spacing.lg, gap: spacing.xs }}>
                <Txt variant="heading" color={readableOn(pv)}>
                  {b.welcome_message || "Welcome"}
                </Txt>
                <View style={{ alignSelf: "flex-start", backgroundColor: sv, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 4, marginTop: spacing.sm }}>
                  <Txt variant="caption" color={readableOn(sv)}>
                    Session {school.academic_session_label}
                  </Txt>
                </View>
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.lg }}>
              <View style={{ flex: 1, height: 40, borderRadius: radius.md, backgroundColor: pv, alignItems: "center", justifyContent: "center" }}>
                <Txt variant="label" color={readableOn(pv)}>Primary button</Txt>
              </View>
              <View style={{ flex: 1, height: 40, borderRadius: radius.md, backgroundColor: tint(pv, 0.9), alignItems: "center", justifyContent: "center" }}>
                <Txt variant="label" color={pv}>Secondary</Txt>
              </View>
            </View>
          </View>
        </View>

        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Logo & banner" />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <Button testID="upload-logo-button" style={{ flex: 1 }} variant="outline" small title={b.logo_file_id ? "Replace logo" : "Upload logo"} loading={uploading === "logo"} icon={<UploadSimple size={16} color={colors.onSurface} />} onPress={() => pick("logo")} />
            <Button testID="upload-banner-button" style={{ flex: 1 }} variant="outline" small title={b.banner_file_id ? "Replace banner" : "Upload banner"} loading={uploading === "banner"} icon={<ImageSquare size={16} color={colors.onSurface} />} onPress={() => pick("banner")} />
          </View>
          {b.logo_file_id || b.banner_file_id ? (
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              {b.logo_file_id ? <Button testID="remove-logo-button" style={{ flex: 1 }} small variant="ghost" title="Use monogram" onPress={() => setB({ ...b, logo_file_id: null })} /> : null}
              {b.banner_file_id ? <Button testID="remove-banner-button" style={{ flex: 1 }} small variant="ghost" title="Remove banner" onPress={() => setB({ ...b, banner_file_id: null })} /> : null}
            </View>
          ) : null}
          <Field testID="brand-monogram-input" label="Monogram (when no logo)" maxLength={3} autoCapitalize="characters" value={b.monogram} onChangeText={(v) => setB({ ...b, monogram: v.toUpperCase() })} />
          <View style={{ gap: spacing.sm }}>
            <Txt variant="label" color={colors.onSurfaceTertiary}>Crest shape</Txt>
            <Segmented testIDPrefix="logo-style" value={b.logo_style} onChange={(v) => setB({ ...b, logo_style: v })} options={[{ value: "circle", label: "Circle" }, { value: "shield", label: "Shield" }, { value: "square", label: "Square" }]} />
          </View>
        </Card>

        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Colours" />
          <Txt variant="label" color={colors.onSurfaceTertiary}>Primary</Txt>
          <Swatches prefix="primary" values={PRESETS} value={b.primary} onPick={(v) => setB({ ...b, primary: v })} />
          <Field testID="brand-primary-input" label="Primary hex" autoCapitalize="characters" value={b.primary} onChangeText={(v) => setB({ ...b, primary: v.trim() })} error={HEX.test(b.primary) ? undefined : "Use a hex value like #1A2B3C"} />
          <Txt variant="label" color={colors.onSurfaceTertiary}>Secondary accent</Txt>
          <Swatches prefix="secondary" values={ACCENTS} value={b.secondary} onPick={(v) => setB({ ...b, secondary: v })} />
          <Field testID="brand-secondary-input" label="Secondary hex" autoCapitalize="characters" value={b.secondary} onChangeText={(v) => setB({ ...b, secondary: v.trim() })} error={HEX.test(b.secondary) ? undefined : "Use a hex value like #1A2B3C"} />
        </Card>

        <Card style={{ gap: spacing.lg }}>
          <SectionTitle title="Messaging" />
          <Field testID="brand-tagline-input" label="Tagline" maxLength={140} value={tagline} onChangeText={setTagline} />
          <Field testID="brand-welcome-input" label="Welcome banner message" maxLength={140} value={b.welcome_message ?? ""} onChangeText={(v) => setB({ ...b, welcome_message: v })} />
        </Card>
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ opened: insets.bottom }}>
        <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: insets.bottom + spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border }}>
          <Button testID="brand-save-button" title="Save brand" disabled={!validHex || !!uploading} loading={save.isPending} onPress={() => save.mutate()} />
        </View>
      </KeyboardStickyView>

      <Sheet visible={!!perm} onClose={() => setPerm(null)} title="Photo access" testID="photo-permission-sheet"
        footer={
          perm?.blocked ? (
            <Button testID="open-settings-button" title="Open Settings" onPress={() => { setPerm(null); Linking.openSettings(); }} />
          ) : (
            <Button testID="allow-photos-button" title="Continue" onPress={async () => {
              const target = perm!.target;
              setPerm(null);
              const r = await ImagePicker.requestMediaLibraryPermissionsAsync();
              if (r.granted) pickNow(target);
              else setPerm({ target, blocked: !r.canAskAgain });
            }} />
          )
        }
      >
        <Txt variant="body">
          {perm?.blocked
            ? "Photo access is turned off for SchoolPulse. Enable it in Settings to upload your school's logo and banner."
            : "Allow access to your photos so you can choose your school's logo and banner. We only upload the image you select."}
        </Txt>
      </Sheet>
    </View>
  );
}
