import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { CaretDown, Check, ChalkboardTeacher, EnvelopeSimple, MapPin, Phone, Student } from "phosphor-react-native";
import React, { useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { api, fileUrl } from "@/src/api";
import { useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { ChildHomeworkCard } from "@/src/components/child-homework-card";
import { Sheet } from "@/src/components/sheet";
import { Badge, Card, EmptyState, ErrorState, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { UpcomingModules } from "@/src/components/upcoming-modules";
import { formatDate, greetingKey, initials } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { radius, spacing, useTheme } from "@/src/theme";
import type { Student as S } from "@/src/types";

export default function ParentHome() {
  const { membership, me } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const sid = membership?.school_id;
  const kids = useQuery({ queryKey: ["parent-children", sid], queryFn: () => api<{ items: S[] }>("/parent/children") });
  const [childId, setChildId] = useState<string | null>(null);
  const [switcher, setSwitcher] = useState(false);
  useEffect(() => {
    if (!childId && kids.data?.items.length) setChildId(kids.data.items[0].id);
  }, [kids.data, childId]);
  const child = useQuery({
    queryKey: ["parent-child", sid, childId],
    enabled: !!childId,
    queryFn: () => api<S & { class_teacher: { name: string } | null; subjects: { subject: string; teacher: string | null }[] }>(`/parent/children/${childId}`),
  });
  const att = useQuery({
    queryKey: ["parent-att", sid, childId],
    enabled: !!childId,
    queryFn: () => api<{ month: string; today: string | null; present: number; absent: number; late: number; days: number }>(`/parent/children/${childId}/attendance`),
  });
  if (!membership) return null;
  const school = membership.school;
  const banner = fileUrl(school.brand.banner_file_id);
  const c = child.data;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
          <SchoolLogo brand={school.brand} size={40} testID="header-school-logo" />
          <View style={{ flex: 1 }}>
            <Txt variant="heading" numberOfLines={1} testID="header-school-name">{school.name}</Txt>
            <Txt variant="caption" numberOfLines={1}>{school.tagline || "Parent Connect"}</Txt>
          </View>
        </View>
      </View>
      <ScrollView refreshControl={<RefreshControl refreshing={kids.isRefetching} onRefresh={() => { kids.refetch(); child.refetch(); }} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}>
        <Animated.View entering={FadeInDown.duration(350)}>
          <View testID="parent-welcome-banner" style={{ borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.brandPrimary }}>
            {banner ? <Image source={{ uri: banner }} style={{ position: "absolute", width: "100%", height: "100%", opacity: 0.35 }} contentFit="cover" /> : null}
            <View style={{ padding: spacing.xl, gap: spacing.xs }}>
              <Txt variant="title" color={colors.onBrandPrimary}>{t(greetingKey())}, {me?.user.name.split(" ")[0]}</Txt>
              <Txt variant="body" color={colors.onBrandPrimary} style={{ opacity: 0.85 }}>{school.brand.welcome_message}</Txt>
            </View>
          </View>
        </Animated.View>

        {kids.isLoading ? (
          <SkeletonList rows={2} />
        ) : kids.isError ? (
          <ErrorState message={(kids.error as Error).message} onRetry={() => kids.refetch()} />
        ) : !kids.data?.items.length ? (
          <Card>
            <EmptyState testID="no-children-state" icon={<Student size={36} color={colors.muted} />} title="No verified children yet" message="Once the school verifies your guardian relationship, your child's details appear here." />
          </Card>
        ) : (
          <>
            <Pressable testID="child-switcher-button" onPress={() => kids.data!.items.length > 1 && setSwitcher(true)}>
              <Card style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
                  <Txt variant="heading" color={colors.onBrandTertiary}>{c ? initials(`${c.first_name} ${c.last_name}`) : ""}</Txt>
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <Txt variant="heading" testID="selected-child-name">{c ? `${c.first_name} ${c.last_name}` : "Loading…"}</Txt>
                  <Txt variant="caption">{c ? `${c.class_name} - ${c.section_name} · Roll ${c.roll_no ?? "—"}` : ""}</Txt>
                </View>
                {kids.data.items.length > 1 ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Txt variant="caption">{kids.data.items.length} children</Txt>
                    <CaretDown size={16} color={colors.muted} />
                  </View>
                ) : <Badge label="Verified" tone="success" />}
              </Card>
            </Pressable>

            {child.isLoading ? <SkeletonList rows={2} /> : child.isError ? <ErrorState message={(child.error as Error).message} onRetry={() => child.refetch()} /> : c ? (
              <>
                <View>
                  <SectionTitle title="Student overview" />
                  <Card style={{ gap: spacing.md }} testID="child-overview-card">
                    {[["Admission no.", c.admission_no], ["Date of birth", formatDate(c.dob)], ["Relationship", c.relation ?? "—"], [t("classTeacher"), c.class_teacher?.name ?? "—"]].map(([k, v]) => (
                      <View key={k} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                        <Txt variant="caption">{k}</Txt>
                        <Txt variant="label" style={{ textTransform: "capitalize" }}>{v}</Txt>
                      </View>
                    ))}
                  </Card>
                </View>
                <View>
                  <SectionTitle title="Attendance this month" />
                  <Card testID="child-attendance-card" style={{ gap: spacing.md }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                      <Txt variant="label">Today</Txt>
                      <Badge testID="child-attendance-today" label={att.data?.today ? att.data.today : "Not marked yet"} tone={att.data?.today === "absent" ? "error" : att.data?.today === "late" ? "warning" : att.data?.today ? "success" : "neutral"} />
                    </View>
                    <View style={{ flexDirection: "row", gap: spacing.md }}>
                      {(["present", "absent", "late"] as const).map((k) => (
                        <View key={k} style={{ flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md }}>
                          <Txt variant="heading" testID={`child-attendance-${k}`}>{att.data?.[k] ?? 0}</Txt>
                          <Txt variant="caption">{k}</Txt>
                        </View>
                      ))}
                    </View>
                  </Card>
                </View>
                <ChildHomeworkCard studentId={c.id} name={`${c.first_name} ${c.last_name}`} />
                {c.subjects.length ? (
                  <View>
                    <SectionTitle title={t("subjects")} />
                    <Card style={{ paddingVertical: 0 }}>
                      {c.subjects.map((s, i) => (
                        <Row key={s.subject + i} last={i === c.subjects.length - 1} icon={<IconTile><ChalkboardTeacher size={18} color={colors.onBrandTertiary} /></IconTile>} title={s.subject} subtitle={s.teacher ?? undefined} />
                      ))}
                    </Card>
                  </View>
                ) : null}
              </>
            ) : null}
          </>
        )}

        <View>
          <SectionTitle title="School contact" />
          <Card style={{ paddingVertical: 0 }}>
            <Row icon={<IconTile><Phone size={18} color={colors.onBrandTertiary} /></IconTile>} title={school.contact?.phone ? `+91 ${school.contact.phone}` : "—"} subtitle="Office" />
            <Row icon={<IconTile><EnvelopeSimple size={18} color={colors.onBrandTertiary} /></IconTile>} title={school.contact?.email || "—"} subtitle="Email" />
            <Row last icon={<IconTile><MapPin size={18} color={colors.onBrandTertiary} /></IconTile>} title={school.contact?.address || "—"} subtitle={school.contact?.city} />
          </Card>
        </View>

        <View>
          <UpcomingModules role="parent" />
        </View>
      </ScrollView>

      <Sheet visible={switcher} onClose={() => setSwitcher(false)} title={t("myChildren")} testID="child-switcher-sheet">
        <View>
          {kids.data?.items.map((k, i) => (
            <Row
              key={k.id}
              testID={`child-option-${k.id}`}
              last={i === kids.data!.items.length - 1}
              icon={<View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}><Txt variant="label" color={colors.onBrandTertiary}>{initials(`${k.first_name} ${k.last_name}`)}</Txt></View>}
              title={`${k.first_name} ${k.last_name}`}
              subtitle={`${k.class_name} - ${k.section_name}`}
              right={k.id === childId ? <Check size={18} color={colors.brandPrimary} weight="bold" /> : <View />}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                setChildId(k.id);
                setSwitcher(false);
              }}
            />
          ))}
        </View>
      </Sheet>
    </View>
  );
}
