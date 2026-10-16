import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { MagnifyingGlass, Plus, UsersThree } from "phosphor-react-native";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api, Paged } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, ChipRow, EmptyState, ErrorState, Row, Segmented, SkeletonList, Txt } from "@/src/components/ui";
import { initials } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { fonts, radius, spacing, type, useTheme } from "@/src/theme";
import type { SchoolClass } from "@/src/types";

type Tab = "students" | "teachers" | "guardians";

function useDebounced(v: string, ms = 300) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const h = setTimeout(() => setD(v), ms);
    return () => clearTimeout(h);
  }, [v, ms]);
  return d;
}

function Avatar({ name }: { name: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }}>
      <Txt variant="label" color={colors.onBrandTertiary}>
        {initials(name)}
      </Txt>
    </View>
  );
}

export default function People() {
  const { membership, can } = useAuth();
  const { t } = useI18n();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [tab, setTab] = useState<Tab>("students");
  const [search, setSearch] = useState("");
  const [classId, setClassId] = useState("all");
  const q = useDebounced(search);
  const sid = membership?.school_id;

  const classes = useQuery({ queryKey: ["classes", sid], queryFn: () => api<Paged<SchoolClass>>("/classes?page_size=100") });

  const list = useInfiniteQuery({
    queryKey: ["people", sid, tab, q, classId],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ page: String(pageParam), page_size: "20", q });
      if (tab === "students" && classId !== "all") params.set("class_id", classId);
      return api<Paged<any>>(`/${tab}?${params.toString()}`);
    },
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const total = list.data?.pages[0]?.total;
  const canAdd = (tab === "students" && can("people.manage")) || (tab === "teachers" && can("staff.manage"));

  const renderItem = ({ item, index }: { item: any; index: number }) => {
    if (tab === "students")
      return (
        <Row
          testID={`student-row-${item.admission_no}`}
          last={index === items.length - 1}
          icon={<Avatar name={`${item.first_name} ${item.last_name}`} />}
          title={`${item.first_name} ${item.last_name}`}
          subtitle={`${item.class_name} - ${item.section_name} · Adm. ${item.admission_no}`}
          onPress={() => router.push(`/student/${item.id}`)}
        />
      );
    if (tab === "teachers")
      return (
        <Row
          testID={`teacher-row-${item.id}`}
          last={index === items.length - 1}
          icon={<Avatar name={item.name} />}
          title={item.name}
          subtitle={`${item.designation} · ${item.assignments.length} assignment${item.assignments.length === 1 ? "" : "s"}`}
          right={item.user_id ? <Badge label="App access" tone="success" /> : undefined}
          onPress={() => router.push(`/teacher/${item.id}`)}
        />
      );
    return (
      <Row
        testID={`guardian-row-${item.id}`}
        last={index === items.length - 1}
        icon={<Avatar name={item.name} />}
        title={item.name}
        subtitle={`+91 ${item.phone}${item.email ? ` · ${item.email}` : ""}`}
        right={item.user_id ? <Badge label="App linked" tone="brand" /> : undefined}
      />
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surfaceSecondary }}>
      <View style={{ paddingTop: insets.top + spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          <View style={{ flexDirection: "row", alignItems: "center", minHeight: 44 }}>
            <Txt variant="title" style={{ flex: 1 }}>
              {t("people")}
            </Txt>
            {total !== undefined ? <Txt variant="caption" testID="people-total">{total} records</Txt> : null}
          </View>
          <Segmented
            testIDPrefix="people-tab"
            value={tab}
            onChange={(v) => {
              setTab(v);
              setSearch("");
            }}
            options={[
              { value: "students", label: t("students") },
              { value: "teachers", label: t("teachers") },
              { value: "guardians", label: t("guardians") },
            ]}
          />
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44 }}>
            <MagnifyingGlass size={18} color={colors.muted} />
            <TextInput
              testID="people-search-input"
              value={search}
              onChangeText={setSearch}
              placeholder={`${t("search")} ${tab}`}
              placeholderTextColor={colors.muted}
              style={{ flex: 1, fontFamily: fonts.regular, fontSize: type.base, color: colors.onSurface, height: 44 }}
            />
          </View>
        </View>
        {tab === "students" ? (
          <ChipRow
            testIDPrefix="class-filter"
            value={classId}
            onChange={setClassId}
            options={[{ value: "all", label: "All classes" }, ...(classes.data?.items.map((c) => ({ value: c.id, label: c.name })) ?? [])]}
          />
        ) : (
          <View style={{ height: spacing.md }} />
        )}
      </View>

      {list.isLoading ? (
        <SkeletonList />
      ) : list.isError ? (
        <ErrorState message={(list.error as Error).message} onRetry={() => list.refetch()} />
      ) : (
        <FlatList
          testID="people-list"
          data={items}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          onEndReachedThreshold={0.4}
          onEndReached={() => list.hasNextPage && !list.isFetchingNextPage && list.fetchNextPage()}
          onRefresh={() => list.refetch()}
          refreshing={list.isRefetching && !list.isFetchingNextPage}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: bottomChrome + 96, flexGrow: 1 }}
          style={{ flex: 1 }}
          ListEmptyComponent={<EmptyState icon={<UsersThree size={40} color={colors.muted} />} title={q ? "No matches" : `No ${tab} yet`} message={q ? "Try a different name or admission number." : undefined} />}
          ListFooterComponent={list.isFetchingNextPage ? <ActivityIndicator color={colors.brandPrimary} style={{ margin: spacing.lg }} /> : null}
        />
      )}

      {canAdd ? (
        <Pressable
          testID={`add-${tab}-fab`}
          onPress={() => router.push(tab === "students" ? "/student-new" : "/teacher-new")}
          style={({ pressed }) => ({
            position: "absolute",
            right: spacing.lg,
            bottom: bottomChrome + spacing.lg,
            height: 52,
            paddingHorizontal: spacing.xl,
            borderRadius: radius.pill,
            backgroundColor: colors.brandPrimary,
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.sm,
            transform: [{ scale: pressed ? 0.96 : 1 }],
            boxShadow: "0px 6px 12px rgba(0, 0, 0, 0.15)",
          })}
        >
          <Plus size={18} color={colors.onBrandPrimary} weight="bold" />
          <Txt variant="label" color={colors.onBrandPrimary}>
            {tab === "students" ? "Add student" : "Add teacher"}
          </Txt>
        </Pressable>
      ) : null}
    </View>
  );
}
