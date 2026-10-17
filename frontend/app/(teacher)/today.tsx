import { useRouter } from "expo-router";
import { BookOpenText, CalendarBlank, Lifebuoy, CalendarCheck, Chalkboard, ChatsCircle, Exam, NotePencil, Student, Table } from "phosphor-react-native";
import React from "react";
import { RefreshControl, ScrollView, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { StaffCheckIn } from "@/src/components/staff-check-in";
import { TeacherWorkspace, useWorkspace } from "@/src/components/teacher-workspace";
import { useTeacherDash } from "@/src/teacher-dash";
import { useAuth } from "@/src/auth";
import { SchoolLogo } from "@/src/components/school-logo";
import { Badge, Card, EmptyState, ErrorState, IconTile, Row, SectionTitle, SkeletonList, Txt } from "@/src/components/ui";
import { UpcomingModules } from "@/src/components/upcoming-modules";
import { greetingKey, todayLabel } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { radius, spacing, useTheme } from "@/src/theme";

export default function TeacherToday() {
  const { membership, me } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const q = useTeacherDash();
  const ws = useWorkspace();
  if (!membership) return null;
  const school = membership.school;
  const d = q.data;
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 }}>
          <SchoolLogo brand={school.brand} size={40} testID="header-school-logo" />
          <View style={{ flex: 1 }}>
            <Txt variant="heading" numberOfLines={1} testID="header-school-name">{school.name}</Txt>
            <Txt variant="caption">Teacher Workspace</Txt>
          </View>
        </View>
      </View>
      <ScrollView refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => { q.refetch(); ws.refetch(); }} tintColor={colors.brandPrimary} />} contentContainerStyle={{ padding: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.xl }}>
        <Animated.View entering={FadeInDown.duration(350)} style={{ gap: spacing.xs }}>
          <Txt variant="caption">{todayLabel()}</Txt>
          <Txt variant="title">{t(greetingKey())}, {me?.user.name.split(" ")[0]}</Txt>
        </Animated.View>
        <StaffCheckIn />
        <TeacherWorkspace />
        {q.isLoading ? (
          <SkeletonList rows={3} />
        ) : q.isError ? (
          <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />
        ) : !d?.sections.length ? (
          <EmptyState icon={<Chalkboard size={40} color={colors.muted} />} title="No classes assigned yet" message="Your school administrator will assign your sections." />
        ) : (
          <>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <Card style={{ flex: 1, gap: spacing.sm }} testID="teacher-stat-sections">
                <IconTile><Chalkboard size={20} color={colors.onBrandTertiary} /></IconTile>
                <Txt variant="title" testID="teacher-stat-sections-value">{d.sections.length}</Txt>
                <Txt variant="caption">{t("assignedClasses")}</Txt>
              </Card>
              <Card style={{ flex: 1, gap: spacing.sm }} testID="teacher-stat-students">
                <IconTile><Student size={20} color={colors.onBrandTertiary} /></IconTile>
                <Txt variant="title" testID="teacher-stat-students-value">{d.total_students}</Txt>
                <Txt variant="caption">{t("students")}</Txt>
              </Card>
            </View>
            <View>
              <Card style={{ paddingVertical: 0 }}>
                <Row testID="teacher-homework-row" icon={<IconTile><NotePencil size={18} color={colors.onBrandTertiary} /></IconTile>} title="Homework" subtitle="Create, publish and track completion" onPress={() => router.push("/homework")} />
                <Row testID="teacher-diary-row" icon={<IconTile><BookOpenText size={18} color={colors.onBrandTertiary} /></IconTile>} title="Class diary" subtitle="Write today's lesson summaries and notes" onPress={() => router.push("/diary")} />
                <Row testID="teacher-timetable-row" icon={<IconTile><Table size={18} color={colors.onBrandTertiary} /></IconTile>} title="My timetable" subtitle="Your periods for the week" onPress={() => router.push("/my-timetable")} />
                <Row testID="teacher-messages-row" icon={<IconTile><ChatsCircle size={18} color={colors.onBrandTertiary} /></IconTile>} title="Parent messages" subtitle="Reply to parents of your classes" onPress={() => router.push("/messages")} />
                <Row testID="teacher-helpdesk-row" icon={<IconTile><Lifebuoy size={18} color={colors.onBrandTertiary} /></IconTile>} title="Help desk" subtitle="Parent requests assigned to you" onPress={() => router.push("/helpdesk")} />
                <Row testID="teacher-ptm-row" icon={<IconTile><CalendarCheck size={18} color={colors.onBrandTertiary} /></IconTile>} title="Parent–teacher meetings" subtitle="Your PTM schedule, availability and notes" onPress={() => router.push("/ptm")} />
                <Row testID="teacher-calendar-row" icon={<IconTile><CalendarBlank size={18} color={colors.onBrandTertiary} /></IconTile>} title="School calendar" subtitle="Events, holidays and exams for your classes" onPress={() => router.push("/calendar")} />
                <Row testID="teacher-exams-row" last icon={<IconTile><Exam size={18} color={colors.onBrandTertiary} /></IconTile>} title="Examinations" subtitle="Enter marks and view results" onPress={() => router.push("/exams")} />
              </Card>
            </View>
            <View>
              <SectionTitle title={t("assignedClasses")} />
              <Card style={{ paddingVertical: 0 }}>
                {d.sections.map((s, i) => (
                  <Row
                    key={s.section_id}
                    testID={`teacher-section-${s.section_id}`}
                    last={i === d.sections.length - 1}
                    icon={<View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}><Txt variant="label" color={colors.onBrandPrimary}>{s.label.split(" - ")[1]}</Txt></View>}
                    title={s.label}
                    subtitle={`${s.students} students · ${s.subjects.join(", ") || "General"}`}
                    right={<Badge testID={`attendance-state-${s.section_id}`} label={s.attendance_marked ? "Marked" : "Attendance pending"} tone={s.attendance_marked ? "success" : "warning"} />}
                    onPress={() => router.push(`/attendance/${s.section_id}`)}
                  />
                ))}
              </Card>
            </View>
          </>
        )}
        <View>
          <UpcomingModules role="teacher" />
        </View>
      </ScrollView>
    </View>
  );
}
