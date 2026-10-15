import { CaretLeft, CaretRight, Lock, WarningCircle } from "phosphor-react-native";
import React from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleProp,
  Text,
  TextInput,
  TextInputProps,
  TextProps,
  View,
  ViewStyle,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { fonts, makeStyles, radius, spacing, type, useTheme } from "@/src/theme";

// ------------------------------------------------------------ Text
type Variant = "display" | "title" | "heading" | "body" | "caption" | "label" | "overline";
export function Txt({
  variant = "body",
  color,
  style,
  ...rest
}: TextProps & { variant?: Variant; color?: string }) {
  const { colors } = useTheme();
  const v = {
    display: { fontSize: type.display, fontFamily: fonts.medium, letterSpacing: -0.6, lineHeight: 36 },
    title: { fontSize: type.xxl, fontFamily: fonts.medium, letterSpacing: -0.4, lineHeight: 30 },
    heading: { fontSize: type.lg, fontFamily: fonts.medium, letterSpacing: -0.1, lineHeight: 22 },
    body: { fontSize: type.base, fontFamily: fonts.regular, lineHeight: 20 },
    caption: { fontSize: type.sm, fontFamily: fonts.regular, lineHeight: 16 },
    label: { fontSize: type.base, fontFamily: fonts.medium, lineHeight: 20 },
    overline: { fontSize: 11, fontFamily: fonts.medium, letterSpacing: 1, lineHeight: 14, textTransform: "uppercase" as const },
  }[variant];
  const defaultColor = variant === "caption" || variant === "overline" ? colors.muted : colors.onSurface;
  return <Text {...rest} style={[v, { color: color ?? defaultColor }, style]} />;
}

// ------------------------------------------------------------ Button
export function Button({
  title,
  onPress,
  variant = "primary",
  loading,
  disabled,
  icon,
  testID,
  style,
  small,
}: {
  title: string;
  onPress?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger" | "outline";
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  testID?: string;
  style?: StyleProp<ViewStyle>;
  small?: boolean;
}) {
  const { colors } = useTheme();
  const palette = {
    primary: { bg: colors.brandPrimary, fg: colors.onBrandPrimary, border: colors.brandPrimary },
    secondary: { bg: colors.brandTertiary, fg: colors.onBrandTertiary, border: colors.brandTertiary },
    ghost: { bg: "transparent", fg: colors.brandPrimary, border: "transparent" },
    outline: { bg: colors.surface, fg: colors.onSurface, border: colors.border },
    danger: { bg: colors.errorSoft, fg: colors.error, border: colors.errorSoft },
  }[variant];
  const off = disabled || loading;
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      disabled={off}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
        onPress?.();
      }}
      style={({ pressed }) => [
        {
          minHeight: small ? 40 : 52,
          paddingHorizontal: small ? spacing.lg : spacing.xl,
          borderRadius: radius.md,
          backgroundColor: palette.bg,
          borderWidth: 1,
          borderColor: palette.border,
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "row",
          gap: spacing.sm,
          opacity: off ? 0.55 : pressed ? 0.85 : 1,
          transform: [{ scale: pressed ? 0.98 : 1 }],
        },
        style,
      ]}
    >
      {loading ? <ActivityIndicator color={palette.fg} /> : icon}
      <Txt variant="label" color={palette.fg}>
        {title}
      </Txt>
    </Pressable>
  );
}

// ------------------------------------------------------------ Card
export function Card({ children, style, testID }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; testID?: string }) {
  const styles = useStyles();
  return (
    <View testID={testID} style={[styles.card, style]}>
      {children}
    </View>
  );
}

// ------------------------------------------------------------ Field
export function Field({
  label,
  error,
  hint,
  ...props
}: TextInputProps & { label: string; error?: string; hint?: string }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const [focus, setFocus] = React.useState(false);
  return (
    <View style={{ gap: spacing.xs + 2 }}>
      <Txt variant="label" color={colors.onSurfaceTertiary}>
        {label}
      </Txt>
      <TextInput
        placeholderTextColor={colors.muted}
        {...props}
        onFocus={(e) => {
          setFocus(true);
          props.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocus(false);
          props.onBlur?.(e);
        }}
        style={[
          styles.input,
          props.multiline && { minHeight: 96, textAlignVertical: "top", paddingTop: spacing.md },
          { borderColor: error ? colors.error : focus ? colors.brandPrimary : colors.border },
          props.style,
        ]}
      />
      {error ? (
        <Txt variant="caption" color={colors.error}>
          {error}
        </Txt>
      ) : hint ? (
        <Txt variant="caption">{hint}</Txt>
      ) : null}
    </View>
  );
}

// ------------------------------------------------------------ Header (sticky, safe-area aware)
export function Header({
  title,
  subtitle,
  back,
  right,
  testID,
}: {
  title: string;
  subtitle?: string;
  back?: boolean;
  right?: React.ReactNode;
  testID?: string;
}) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]} testID={testID}>
      <View style={styles.headerRow}>
        {back ? (
          <Pressable
            testID="header-back-button"
            accessibilityLabel="Go back"
            onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
            style={styles.backBtn}
            hitSlop={8}
          >
            <CaretLeft size={22} color={colors.onSurface} />
          </Pressable>
        ) : null}
        <View style={{ flex: 1 }}>
          <Txt variant={back ? "heading" : "title"} numberOfLines={1}>
            {title}
          </Txt>
          {subtitle ? (
            <Txt variant="caption" numberOfLines={1}>
              {subtitle}
            </Txt>
          ) : null}
        </View>
        {right}
      </View>
    </View>
  );
}

// ------------------------------------------------------------ Rows, tiles
export function IconTile({ children, tone }: { children: React.ReactNode; tone?: string }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        width: 40,
        height: 40,
        borderRadius: radius.md,
        backgroundColor: tone ?? colors.brandTertiary,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {children}
    </View>
  );
}

export function Row({
  icon,
  title,
  subtitle,
  onPress,
  right,
  testID,
  last,
}: {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  onPress?: () => void;
  right?: React.ReactNode;
  testID?: string;
  last?: boolean;
}) {
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <Pressable
      testID={testID}
      disabled={!onPress}
      onPress={onPress}
      style={({ pressed }) => [styles.row, !last && styles.rowBorder, pressed && { backgroundColor: colors.surfaceSecondary }]}
    >
      {icon}
      <View style={{ flex: 1, gap: 2 }}>
        <Txt variant="label" numberOfLines={1}>
          {title}
        </Txt>
        {subtitle ? (
          <Txt variant="caption" numberOfLines={2}>
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {right ?? (onPress ? <CaretRight size={18} color={colors.muted} /> : null)}
    </Pressable>
  );
}

export function Badge({ label, tone = "neutral", testID }: { label: string; tone?: "neutral" | "success" | "warning" | "brand" | "error"; testID?: string }) {
  const { colors } = useTheme();
  const p = {
    neutral: [colors.surfaceTertiary, colors.onSurfaceTertiary],
    success: [colors.successSoft, "#047857"],
    warning: [colors.warningSoft, "#B45309"],
    error: [colors.errorSoft, colors.error],
    brand: [colors.brandTertiary, colors.onBrandTertiary],
  }[tone];
  return (
    <View testID={testID} style={{ backgroundColor: p[0], paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill, alignSelf: "flex-start" }}>
      <Txt variant="caption" color={p[1]} style={{ fontFamily: fonts.medium }}>
        {label}
      </Txt>
    </View>
  );
}

// ------------------------------------------------------------ Chips (horizontal, never wrap)
export function ChipRow<T extends string>({
  options,
  value,
  onChange,
  testIDPrefix,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  testIDPrefix: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ height: 56, justifyContent: "center" }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: spacing.lg }}>
        {options.map((o) => {
          const active = o.value === value;
          return (
            <Pressable
              key={o.value}
              testID={`${testIDPrefix}-${o.value}`}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                onChange(o.value);
              }}
              style={{
                flexShrink: 0,
                height: 36,
                paddingHorizontal: spacing.lg,
                borderRadius: radius.pill,
                justifyContent: "center",
                borderWidth: 1,
                backgroundColor: active ? colors.brandPrimary : colors.surface,
                borderColor: active ? colors.brandPrimary : colors.border,
              }}
            >
              <Txt variant="label" color={active ? colors.onBrandPrimary : colors.onSurfaceTertiary}>
                {o.label}
              </Txt>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

// ------------------------------------------------------------ states
export function LoadingState({ testID = "loading-state" }: { testID?: string }) {
  const { colors } = useTheme();
  return (
    <View testID={testID} style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xxl }}>
      <ActivityIndicator color={colors.brandPrimary} />
    </View>
  );
}

export function SkeletonList({ rows = 5 }: { rows?: number }) {
  const { colors } = useTheme();
  return (
    <View testID="skeleton-list" style={{ gap: spacing.md, padding: spacing.lg }}>
      {Array.from({ length: rows }).map((_, i) => (
        <View key={i} style={{ height: 64, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary, opacity: 1 - i * 0.12 }} />
      ))}
    </View>
  );
}

export function EmptyState({ icon, title, message, action, testID = "empty-state" }: { icon?: React.ReactNode; title: string; message?: string; action?: React.ReactNode; testID?: string }) {
  return (
    <View testID={testID} style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xxl, gap: spacing.md }}>
      {icon}
      <Txt variant="heading" style={{ textAlign: "center" }}>
        {title}
      </Txt>
      {message ? (
        <Txt variant="body" color={undefined} style={{ textAlign: "center", opacity: 0.7 }}>
          {message}
        </Txt>
      ) : null}
      {action}
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  const { colors } = useTheme();
  return (
    <EmptyState
      testID="error-state"
      icon={<WarningCircle size={40} color={colors.error} />}
      title="Couldn't load this"
      message={message}
      action={onRetry ? <Button testID="retry-button" small variant="outline" title="Try again" onPress={onRetry} /> : undefined}
    />
  );
}

export function SectionTitle({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md }}>
      <Txt variant="overline">{title}</Txt>
      {action}
    </View>
  );
}

export function ComingSoonRow({ title, subtitle, last }: { title: string; subtitle: string; last?: boolean }) {
  const { colors } = useTheme();
  return (
    <Row
      testID={`coming-soon-${title.toLowerCase().replace(/[^a-z]+/g, "-")}`}
      icon={
        <IconTile tone={colors.surfaceTertiary}>
          <Lock size={18} color={colors.muted} />
        </IconTile>
      }
      title={title}
      subtitle={subtitle}
      last={last}
      right={<Badge label="Coming soon" />}
    />
  );
}

// ------------------------------------------------------------ Segmented
export function Segmented<T extends string>({ options, value, onChange, testIDPrefix }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; testIDPrefix: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderRadius: radius.md, padding: 4 }}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            testID={`${testIDPrefix}-${o.value}`}
            onPress={() => onChange(o.value)}
            style={{ flex: 1, height: 36, borderRadius: radius.sm + 2, alignItems: "center", justifyContent: "center", backgroundColor: active ? colors.surface : "transparent" }}
          >
            <Txt variant="label" color={active ? colors.onSurface : colors.muted}>
              {o.label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  card: {
    backgroundColor: c.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: c.border,
    padding: spacing.lg,
    shadowColor: "#0A192F",
    shadowOpacity: 0.04,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 1,
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    fontSize: type.lg,
    fontFamily: fonts.regular,
    color: c.onSurface,
    backgroundColor: c.surface,
  },
  header: {
    backgroundColor: c.surface,
    borderBottomWidth: 1,
    borderBottomColor: c.divider,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 44 },
  backBtn: { width: 44, height: 44, marginLeft: -spacing.sm, alignItems: "center", justifyContent: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, minHeight: 60 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: c.divider },
}));
