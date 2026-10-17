import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { BookOpenText, Books, CalendarCheck, ChartLineUp, ChatsCircle, Exam, Megaphone, Table, ChalkboardTeacher, IdentificationBadge, NotePencil, PaintBrush, Student, UserPlus, Users, UsersThree } from "phosphor-react-native";
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, fileUrl } from "@/src/api";
import { useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { Badge, Card, ErrorState, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { UpcomingModules } from "@/src/components/upcoming-modules";
import { formatDateTime, greetingKey, ROLE_LABEL, todayLabel } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { radius, spacing, useTheme } from "@/src/theme";

type Dash = {
  academic_year: { name: string } | null;
  counts: Record<string, number>;
  gender: Record<string, number>;
  by_class: { class_id: string; name: string; students: number; sections: number }[];
  recent_activity: { id: string; action: string; at: string; entity: string }[];
};

function Stat({ label, value, icon, testID, delay }: { label: string; value: number | string; icon: React.ReactNode; testID: string; delay: number }) {
  const { colors } = useTheme();
  return (
    <Animated.View entering={FadeInDown.delay(delay).duration(350)} style={{ flexBasis: "47%", flexGrow: 1 }}>
      <Card testID={testID} style={{ gap: spacing.md }}>
        <IconTile>{icon}</IconTile>
        <View>
          <Txt variant="title" testID={`${testID}-value`}>
            {value}
          </Txt>
          <Txt variant="caption" color={colors.muted}>
            {label}
          </Txt>
        </View>
      </Card>
    </Animated.View>
  );
}

export default function CommandCentre() {
  const { membership, me, can } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const q = useQuery({ queryKey: ["owner-dash", membership?.school_id], queryFn: () => api<Dash>("/dashboard/owner") });
  const att = useQuery({
    queryKey: ["att-today", membership?.school_id],
    queryFn: () => api<{ sections_marked: number; sections_total: number; present: number; absent: number; late: number; rate: number | null; trend: { date: string; rate: number | null }[] }>("/attendance/summary/today"),
  });
  const staff = useQuery({
    queryKey: ["staff-today", membership?.school_id],
    queryFn: () => api<{ total: number; present: number; late: number; absent: number; half_day: number; on_leave: number; unmarked: number; pending_leave: number }>("/staff/summary/today"),
  });
  const hw = useQuery({
    queryKey: ["hw-summary", membership?.school_id],
    queryFn: () => api<{ published_this_week: number; due_today: number; drafts: number; sections_with_homework_this_week: number; sections_total: number }>("/homework/summary"),
  });
  const diary = useQuery({
    queryKey: ["diary-summary", membership?.school_id],
    queryFn: () => api<{ sections_with_diary: number; sections_total: number; entries: number }>("/diary/summary/today"),
  });
  if (!membership) return null;
  const school = membership.school;
  const c = q.data?.counts;
  const maxClass = Math.max(1, ...(q.data?.by_class.map((b) => b.students) ?? [1]));
  const banner = fileUrl(school.brand.banner_file_id);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
          <SchoolLogo brand={school.brand} size={40} testID="header-school-logo" />
          <View style={{ flex: 1 }}>
            <Txt variant="heading" numberOfLines={1} testID="header-school-name">
              {school.name}
            </Txt>
            <Txt variant="caption" numberOfLines={1}>
              {t("commandCentre")} · {ROLE_LABEL[membership.role]}
            </Txt>
          </View>
        </View>
      </View>
      <ScrollView
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); att.refetch(); staff.refetch(); }} tintColor={colors.brandPrimary} />}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}
      >
        <Animated.View entering={FadeInDown.duration(350)}>
          <View testID="welcome-banner" style={{ borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.brandPrimary }}>
            {banner ? <Image source={{ uri: banner }} style={{ position: "absolute", width: "100%", height: "100%", opacity: 0.35 }} contentFit="cover" /> : null}
            <View style={{ padding: spacing.xl, gap: spacing.xs }}>
              <Txt variant="caption" color={colors.onBrandPrimary} style={{ opacity: 0.8 }}>
                {todayLabel()}
              </Txt>
              <Txt variant="title" color={colors.onBrandPrimary}>
                {t(greetingKey())}, {me?.user.name.split(" ")[0]}
              </Txt>
              <Txt variant="body" color={colors.onBrandPrimary} style={{ opacity: 0.85 }}>
                {school.brand.welcome_message || school.tagline}
              </Txt>
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                <View style={{ backgroundColor: colors.brandSecondary, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 4 }}>
                  <Txt variant="caption" color={colors.onBrandSecondary}>
                    Session {q.data?.academic_year?.name ?? school.academic_session_label ?? "—"}
                  </Txt>
                </View>
              </View>
            </View>
          </View>
        </Animated.View>

        {q.isLoading ? (
          <SkeletonList rows={4} />
        ) : q.isError ? (
          <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
        ) : c ? (
          <>
            <View>
              <SectionTitle title={t("schoolOverview")} action={<Badge label={t("liveFromRecords")} tone="success" />} />
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                <Stat testID="stat-students" delay={50} label={t("students")} value={c.students} icon={<Student size={20} color={colors.onBrandTertiary} />} />
                <Stat testID="stat-teachers" delay={100} label={t("teachers")} value={c.teachers} icon={<ChalkboardTeacher size={20} color={colors.onBrandTertiary} />} />
                <Stat testID="stat-guardians" delay={150} label={t("guardians")} value={c.guardians} icon={<Users size={20} color={colors.onBrandTertiary} />} />
                <Stat testID="stat-sections" delay={200} label={`${c.classes} classes · ${t("sections")}`} value={c.sections} icon={<Books size={20} color={colors.onBrandTertiary} />} />
              </View>
            </View>

            {att.data ? (
              <Card testID="attendance-today-card" style={{ gap: spacing.md }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Txt variant="label">Today&apos;s attendance</Txt>
                  <Txt variant="label" testID="attendance-today-rate">{att.data.rate === null ? "—" : `${att.data.rate}%`}</Txt>
                </View>
                <Txt variant="caption" testID="attendance-today-detail">
                  {att.data.sections_marked}/{att.data.sections_total} · P {att.data.present} · A {att.data.absent} · L {att.data.late}
                </Txt>
                <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 6, height: 48 }}>
                  {att.data.trend.map((d) => (
                    <View key={d.date} style={{ flex: 1, height: d.rate === null ? 4 : Math.max(4, (d.rate / 100) * 48), borderRadius: 3, backgroundColor: d.rate === null ? colors.surfaceTertiary : colors.brandSecondary }} />
                  ))}
                </View>
                <Txt variant="caption">Last 7 days · sections marked today</Txt>
              </Card>
            ) : null}
            {staff.data ? (
              <Card testID="staff-today-card" style={{ gap: spacing.md }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Txt variant="label">Staff today</Txt>
                  <Txt variant="label" testID="staff-today-present">{staff.data.present + staff.data.late + staff.data.half_day}/{staff.data.total}</Txt>
                </View>
                <Txt variant="caption" testID="staff-today-detail">
                  Late {staff.data.late} · Absent {staff.data.absent} · Leave {staff.data.on_leave} · Unmarked {staff.data.unmarked}
                </Txt>
                {staff.data.pending_leave ? <Badge testID="staff-pending-leave" tone="warning" label={`${staff.data.pending_leave} leave request(s) awaiting approval`} /> : null}
              </Card>
            ) : null}
            <Card testID="guardian-verification-card" style={{ gap: spacing.md }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Txt variant="label">Verified guardian links</Txt>
                <Txt variant="label" testID="verified-links-value">
                  {c.verified_guardian_links}/{c.guardian_links}
                </Txt>
              </View>
              <View style={{ height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" }}>
                <View style={{ height: 8, width: `${c.guardian_links ? (c.verified_guardian_links / c.guardian_links) * 100 : 0}%`, backgroundColor: colors.brandSecondary }} />
              </View>
              <Txt variant="caption">Only verified guardians can see a child&apos;s records in Parent Connect.</Txt>
            </Card>

            <View>
              <SectionTitle title={t("studentsByClass")} />
              <Card testID="class-distribution-card" style={{ gap: spacing.md }}>
                {q.data!.by_class.length === 0 ? (
                  <Txt variant="caption">No classes yet. Add them in Academics.</Txt>
                ) : (
                  q.data!.by_class.map((b) => (
                    <View key={b.class_id} style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                      <Txt variant="caption" style={{ width: 64 }} color={colors.onSurfaceTertiary}>
                        {b.name}
                      </Txt>
                      <View style={{ flex: 1, height: 10, borderRadius: 5, backgroundColor: colors.surfaceTertiary, overflow: "hidden" }}>
                        <View style={{ height: 10, borderRadius: 5, width: `${(b.students / maxClass) * 100}%`, backgroundColor: colors.brandPrimary }} />
                      </View>
                      <Txt variant="label" style={{ width: 28, textAlign: "right" }}>
                        {b.students}
                      </Txt>
                    </View>
                  ))
                )}
              </Card>
            </View>
          </>
        ) : null}

        <View>
          <SectionTitle title={t("quickActions")} />
          <Card style={{ paddingVertical: 0 }}>
            {can("brand.manage") ? (
              <Row testID="quick-brand-studio" icon={<IconTile><PaintBrush size={18} color={colors.onBrandTertiary} /></IconTile>} title={t("brandStudio")} subtitle="Logo, colours and welcome banner" onPress={() => router.push("/brand-studio")} />
            ) : null}
            {can("people.manage") ? (
              <Row testID="quick-add-student" icon={<IconTile><UserPlus size={18} color={colors.onBrandTertiary} /></IconTile>} title={t("addStudent")} subtitle="Admission record with class placement" onPress={() => router.push("/student-new")} />
            ) : null}
            {can("staff.manage") ? (
              <Row testID="quick-staff-attendance" icon={<IconTile><IdentificationBadge size={18} color={colors.onBrandTertiary} /></IconTile>} title="Staff attendance" subtitle="Daily register and check-ins" onPress={() => router.push("/staff-attendance")} />
            ) : null}
            {can("staff.manage") ? (
              <Row testID="quick-leave-approvals" icon={<IconTile><CalendarCheck size={18} color={colors.onBrandTertiary} /></IconTile>} title="Leave requests" subtitle={staff.data?.pending_leave ? `${staff.data.pending_leave} awaiting decision` : "Approve or reject teacher leave"} onPress={() => router.push("/leave-approvals")} />
            ) : null}
            {can("academic.manage") ? (
              <Row testID="quick-homework" icon={<IconTile><NotePencil size={18} color={colors.onBrandTertiary} /></IconTile>} title="Homework" subtitle={hw.data ? `${hw.data.published_this_week} published this week · ${hw.data.sections_with_homework_this_week}/${hw.data.sections_total} sections` : "All sections"} onPress={() => router.push("/homework")} />
            ) : null}
            {can("academic.manage") ? (
              <Row testID="quick-diary" icon={<IconTile><BookOpenText size={18} color={colors.onBrandTertiary} /></IconTile>} title="Class diary" subtitle={diary.data ? `${diary.data.sections_with_diary}/${diary.data.sections_total} sections updated today` : "Daily class updates"} onPress={() => router.push("/diary")} />
            ) : null}
            {can("academic.manage") ? (
              <Row testID="quick-timetable" icon={<IconTile><Table size={18} color={colors.onBrandTertiary} /></IconTile>} title="Timetable" subtitle="Bell schedule, class periods, clash checks" onPress={() => router.push("/timetable")} />
            ) : null}
            {can("academic.manage") ? (
              <Row testID="quick-exams" icon={<IconTile><Exam size={18} color={colors.onBrandTertiary} /></IconTile>} title="Examinations" subtitle="Exams, marks progress, results and report cards" onPress={() => router.push("/exams")} />
            ) : null}
            {can("academic.manage") ? (
              <Row testID="quick-insights" icon={<IconTile><ChartLineUp size={18} color={colors.onBrandTertiary} /></IconTile>} title="Academic insights" subtitle="Attendance, coverage, results and staff trends" onPress={() => router.push("/academic-insights")} />
            ) : null}
            {can("notices.manage") ? (
              <Row testID="quick-escalations" icon={<IconTile><ChatsCircle size={18} color={colors.onBrandTertiary} /></IconTile>} title="Escalated messages" subtitle="Parent–teacher conversations needing the office" onPress={() => router.push("/messages")} />
            ) : null}
            {can("notices.manage") ? (
              <Row testID="quick-notices" icon={<IconTile><Megaphone size={18} color={colors.onBrandTertiary} /></IconTile>} title="Notices" subtitle="Publish announcements, track reads and acknowledgements" onPress={() => router.push("/notices")} />
            ) : null}
            <Row testID="quick-academics" icon={<IconTile><Books size={18} color={colors.onBrandTertiary} /></IconTile>} title={t("academicSetup")} subtitle="Years, classes, sections and subjects" onPress={() => router.push("/academics")} />
            <Row testID="quick-people" last icon={<IconTile><UsersThree size={18} color={colors.onBrandTertiary} /></IconTile>} title={t("directory")} subtitle={c ? `${c.students} students · ${c.staff_members} staff accounts` : undefined} onPress={() => router.push("/people")} />
          </Card>
        </View>

        {q.data?.recent_activity.length ? (
          <View>
            <SectionTitle title={t("recentActivity")} />
            <Card style={{ paddingVertical: spacing.sm }} testID="recent-activity-card">
              {q.data.recent_activity.map((a) => (
                <View key={a.id} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.sm, gap: spacing.md }}>
                  <Txt variant="body" style={{ flex: 1 }} numberOfLines={1}>
                    {a.action.replace(/[._]/g, " ")}
                  </Txt>
                  <Txt variant="caption">{formatDateTime(a.at)}</Txt>
                </View>
              ))}
            </Card>
          </View>
        ) : null}

        <View>
          <UpcomingModules role={membership.role} />
        </View>
      </ScrollView>
    </View>
  );
}
