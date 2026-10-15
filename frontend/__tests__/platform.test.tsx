import { act, render, renderHook, screen, fireEvent } from "@testing-library/react-native";
import { execFileSync } from "child_process";
import path from "path";
import React from "react";

import { homeRoute } from "@/src/auth";
import { EmptyState, ErrorState, LoadingState, Txt } from "@/src/components/ui";
import { setLang, translate } from "@/src/i18n";
import { DEFAULT_BRAND, readableOn, setBrandColors, useTheme } from "@/src/theme";
import type { Me, Membership } from "@/src/types";

const mem = (role: any, id = "s1"): Membership => ({ school_id: id, role, permissions: [], school: { id, name: id, slug: id, status: "active", brand: { primary: "#14532D", secondary: "#65A30D", monogram: "GP", logo_style: "circle" }, contact: {} } as any });
const me = (memberships: Membership[], platform_role: string | null = null): Me => ({ user: { id: "u", email: "e", name: "N", platform_role }, memberships });

describe("role-based routing", () => {
  it("routes each role to its own workspace", () => {
    expect(homeRoute(me([mem("owner")]), mem("owner"))).toBe("/command");
    expect(homeRoute(me([mem("principal")]), mem("principal"))).toBe("/command");
    expect(homeRoute(me([mem("teacher")]), mem("teacher"))).toBe("/today");
    expect(homeRoute(me([mem("parent")]), mem("parent"))).toBe("/family");
  });
  it("asks multi-school users to choose a school (school switching)", () => {
    expect(homeRoute(me([mem("parent", "a"), mem("parent", "b")]), null)).toBe("/select-school");
  });
  it("super admin without membership goes to platform; others to no-access; signed-out to login", () => {
    expect(homeRoute(me([], "super_admin"), null)).toBe("/platform");
    expect(homeRoute(me([]), null)).toBe("/no-access"); // e.g. only school got suspended
    expect(homeRoute(null, null)).toBe("/login");
  });
});

describe("tenant branding", () => {
  it("applies and clears school brand colours at runtime", async () => {
    const { result } = await renderHook(() => useTheme());
    await act(async () => setBrandColors("#14532D", "#65A30D"));
    expect(result.current.colors.brandPrimary).toBe("#14532D");
    expect(result.current.colors.brandSecondary).toBe("#65A30D");
    expect(result.current.colors.onBrandPrimary).toBe("#FFFFFF");
    await act(async () => setBrandColors(null));
    expect(result.current.colors.brandPrimary).toBe(DEFAULT_BRAND.primary);
  });
  it("picks readable text on light brand colours", () => {
    expect(readableOn("#FDE68A")).toBe("#111827");
  });
});

describe("language switching", () => {
  afterEach(async () => { await act(async () => { await setLang("en"); }); });
  it("falls back to English and translates catalogue + patterns", () => {
    expect(translate("en", "Save brand")).toBe("Save brand");
    expect(translate("hi", "Save brand")).toBe("ब्रांड सहेजें");
    expect(translate("hi", "Some brand new string")).toBe("Some brand new string");
    expect(translate("hi", "Too many failed attempts. Try again in 30 seconds.")).toContain("30");
  });
  it("Txt re-renders in Hindi but never translates raw user data", async () => {
    await render(<><Txt>Sign out</Txt><Txt raw>Sign out</Txt></>);
    expect(screen.getAllByText("Sign out")).toHaveLength(2);
    await act(async () => { await setLang("hi"); });
    expect(screen.getByText("साइन आउट")).toBeTruthy();
    expect(screen.getByText("Sign out")).toBeTruthy();
  });
  it("has Hindi for every static UI string (hard-coded string guard)", () => {
    const out = execFileSync("node", [path.join(__dirname, "../scripts/i18n-check.js")]).toString();
    expect(out).toMatch(/Missing: 0/);
  });
});

describe("loading / empty / error states", () => {
  it("renders loading and empty states", async () => {
    await render(<><LoadingState /><EmptyState title="No schools yet" message="Add your first school tenant." /></>);
    expect(screen.getByTestId("loading-state")).toBeTruthy();
    expect(screen.getByText("No schools yet")).toBeTruthy();
  });
  it("error state retries", async () => {
    const retry = jest.fn();
    await render(<ErrorState message="boom" onRetry={retry} />);
    await fireEvent.press(screen.getByTestId("retry-button"));
    expect(retry).toHaveBeenCalled();
  });
});
