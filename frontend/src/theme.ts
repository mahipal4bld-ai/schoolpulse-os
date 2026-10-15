// Design tokens for SchoolPulse OS (light theme). Keys match the "color" block of
// /app/design_guidelines.json. Brand keys are overridden at runtime per school tenant
// through setBrandColors(); every useTheme()/makeStyles consumer re-renders.

import { useMemo, useSyncExternalStore } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FFFFFF",
  onSurface: "#111827",
  surfaceSecondary: "#F9FAFB",
  onSurfaceSecondary: "#1F2937",
  surfaceTertiary: "#F3F4F6",
  onSurfaceTertiary: "#374151",
  surfaceInverse: "#111827",
  onSurfaceInverse: "#FFFFFF",
  muted: "#6B7280",

  brand: "#0A192F",
  onBrand: "#FFFFFF",
  brandPrimary: "#0A192F",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#0D9488",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#E0E7FF",
  onBrandTertiary: "#0A192F",

  success: "#10B981",
  onSuccess: "#FFFFFF",
  successSoft: "#ECFDF5",
  warning: "#F59E0B",
  onWarning: "#FFFFFF",
  warningSoft: "#FFFBEB",
  error: "#EF4444",
  onError: "#FFFFFF",
  errorSoft: "#FEF2F2",
  info: "#3B82F6",
  onInfo: "#FFFFFF",

  border: "#E5E7EB",
  borderStrong: "#D1D5DB",
  divider: "#F3F4F6",
  backdrop: "rgba(17,24,39,0.45)",
};

export type ThemeColors = typeof light;

export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light };

export const DEFAULT_BRAND = { primary: light.brandPrimary, secondary: light.brandSecondary };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}
setColorScheme?.(themes.dark ? null : defaultScheme);

// ------------------------------------------------------------ tenant brand override
function hexToRgb(hex: string) {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
export function tint(hex: string, amount: number) {
  const [r, g, b] = hexToRgb(hex);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  return `#${[mix(r), mix(g), mix(b)].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}
export function readableOn(hex: string) {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.45 ? "#111827" : "#FFFFFF";
}
export function brandPalette(primary: string, secondary: string): Partial<ThemeColors> {
  return {
    brand: primary,
    onBrand: readableOn(primary),
    brandPrimary: primary,
    onBrandPrimary: readableOn(primary),
    brandSecondary: secondary,
    onBrandSecondary: readableOn(secondary),
    brandTertiary: tint(primary, 0.9),
    onBrandTertiary: primary,
  };
}

let override: Partial<ThemeColors> = {};
const listeners = new Set<() => void>();
export function setBrandColors(primary?: string | null, secondary?: string | null) {
  override = primary ? brandPalette(primary, secondary || DEFAULT_BRAND.secondary) : {};
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const snapshot = () => override;

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const ov = useSyncExternalStore(subscribe, snapshot, snapshot);
  const scheme: ColorScheme = (system === "dark" || system === "light") && themes[system] ? system : defaultScheme;
  const colors = useMemo(() => ({ ...(themes[scheme] ?? themes.light), ...ov }), [scheme, ov]);
  return { scheme, colors };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}

// ------------------------------------------------------------ design tokens
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };
export const fonts = { regular: "Jakarta-400", medium: "Jakarta-500", semibold: "Jakarta-600" };
export const type = { sm: 12, base: 14, lg: 16, xl: 20, xxl: 24, display: 30 };
