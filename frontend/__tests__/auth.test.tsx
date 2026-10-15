import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text } from "react-native";

import { session } from "@/src/api";
import { AuthProvider, useAuth } from "@/src/auth";
import { queryClient } from "@/src/query-client";
import { useTheme } from "@/src/theme";

jest.mock("react-native-safe-area-context", () => require("react-native-safe-area-context/jest/mock").default);

const school = (id: string, primary: string, status = "active") => ({
  id, name: `School ${id}`, slug: id, status, brand: { primary, secondary: "#0D9488", monogram: id.toUpperCase(), logo_style: "circle", welcome_message: "Hi" }, contact: {},
});
const membership = (id: string, role: string, primary: string) => ({ school_id: id, role, permissions: role === "owner" ? ["brand.manage"] : [], school: school(id, primary) });
const ME = { user: { id: "u1", email: "p@x.com", name: "Pat Parent", platform_role: null }, memberships: [membership("a", "parent", "#9A3412"), membership("b", "owner", "#14532D")] };

let routes: Record<string, (body: any, n: number) => { status: number; body: any }>;
let counts: Record<string, number>;
beforeEach(() => {
  counts = {};
  queryClient.clear();
  (global as any).fetch = jest.fn(async (url: string, init: any) => {
    const key = `${init?.method || "GET"} ${url.replace(/^.*\/api/, "").split("?")[0]}`;
    counts[key] = (counts[key] || 0) + 1;
    const h = routes[key];
    const r = h ? h(init?.body ? JSON.parse(init.body) : null, counts[key]) : { status: 404, body: { detail: "nf" } };
    return { ok: r.status < 400, status: r.status, text: async () => JSON.stringify(r.body), json: async () => r.body };
  });
});

function Probe() {
  const a = useAuth();
  const { colors } = useTheme();
  return (
    <>
      <Text testID="status">{a.status}</Text>
      <Text testID="school">{a.membership?.school_id ?? "none"}</Text>
      <Text testID="brand">{colors.brandPrimary}</Text>
      <Text testID="can-brand">{String(a.can("brand.manage"))}</Text>
      <Text testID="login" onPress={() => a.login("p@x.com", "pw").catch(() => {})}>login</Text>
      <Text testID="pick-a" onPress={() => a.selectSchool("a")}>a</Text>
      <Text testID="pick-b" onPress={() => a.selectSchool("b")}>b</Text>
      <Text testID="logout" onPress={() => a.logout()}>logout</Text>
    </>
  );
}
const mount = () => render(<QueryClientProvider client={queryClient}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
const tid = (id: string) => screen.getByTestId(id).props.children;

describe("AuthProvider", () => {
  beforeEach(() => {
    routes = {
      "POST /auth/login": () => ({ status: 200, body: { access_token: "A1", refresh_token: "R1", ...ME } }),
      "POST /auth/logout": () => ({ status: 200, body: { ok: true } }),
      "GET /auth/me": () => ({ status: 200, body: ME }),
    };
  });

  it("starts signed out, logs in and requires school choice for multi-school users", async () => {
    await mount();
    await waitFor(() => expect(tid("status")).toBe("signedOut"));
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    await waitFor(() => expect(tid("status")).toBe("signedIn"));
    expect(tid("school")).toBe("none");
  });

  it("switching school changes tenant header, permissions and brand", async () => {
    await mount();
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    await act(async () => { await fireEvent.press(screen.getByTestId("pick-a")); });
    expect(session.getSchool()).toBe("a");
    expect(tid("brand")).toBe("#9A3412");
    expect(tid("can-brand")).toBe("false");
    await act(async () => { await fireEvent.press(screen.getByTestId("pick-b")); });
    expect(session.getSchool()).toBe("b");
    expect(tid("brand")).toBe("#14532D");
    expect(tid("can-brand")).toBe("true");
  });

  it("logout clears the session and calls the server", async () => {
    await mount();
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    await act(async () => { await fireEvent.press(screen.getByTestId("logout")); });
    expect(tid("status")).toBe("signedOut");
    expect(counts["POST /auth/logout"]).toBe(1);
  });

  it("expired session with failed refresh signs the user out", async () => {
    routes["GET /school"] = () => ({ status: 401, body: { detail: "Access token expired" } });
    routes["POST /auth/refresh"] = () => ({ status: 401, body: { detail: "Refresh token reuse detected" } });
    await mount();
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    const { api } = require("@/src/api");
    await act(async () => { await api("/school").catch(() => {}); });
    await waitFor(() => expect(tid("status")).toBe("signedOut"));
  });

  it("suspended school is dropped from memberships after a 403", async () => {
    await mount();
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    await act(async () => { await fireEvent.press(screen.getByTestId("pick-b")); });
    routes["GET /school"] = () => ({ status: 403, body: { detail: "This school account is not active" } });
    routes["GET /auth/me"] = () => ({ status: 200, body: { ...ME, memberships: [ME.memberships[0]] } });
    const { api } = require("@/src/api");
    await act(async () => { await api("/school").catch(() => {}); });
    await waitFor(() => expect(tid("school")).toBe("a"));
    expect(tid("brand")).toBe("#9A3412");
  });
});

describe("Parent child switching", () => {
  it("shows first verified child and switches via the sheet", async () => {
    const kids = [
      { id: "k1", first_name: "Aarav", last_name: "Sharma", class_name: "Class 1", section_name: "A", roll_no: 1, admission_no: "SV1", dob: "2019-01-01" },
      { id: "k2", first_name: "Diya", last_name: "Sharma", class_name: "Class 3", section_name: "B", roll_no: 4, admission_no: "SV2", dob: "2017-01-01" },
    ];
    const single = { ...ME, memberships: [ME.memberships[0]] };
    routes = {
      "POST /auth/login": () => ({ status: 200, body: { access_token: "A", refresh_token: "R", ...single } }),
      "GET /parent/children": () => ({ status: 200, body: { items: kids } }),
      "GET /parent/children/k1": () => ({ status: 200, body: { ...kids[0], relation: "father", class_teacher: null, subjects: [] } }),
      "GET /parent/children/k2": () => ({ status: 200, body: { ...kids[1], relation: "father", class_teacher: null, subjects: [] } }),
    };
    const ParentHome = require("@/app/(parent)/family").default;
    function Harness() {
      const a = useAuth();
      return a.membership ? <ParentHome /> : <Text testID="login" onPress={() => a.login("p@x.com", "pw")}>login</Text>;
    }
    await render(<QueryClientProvider client={queryClient}><AuthProvider><Harness /></AuthProvider></QueryClientProvider>);
    await waitFor(() => screen.getByTestId("login"));
    await act(async () => { await fireEvent.press(screen.getByTestId("login")); });
    await waitFor(() => expect(screen.getByTestId("selected-child-name").props.children).toBe("Aarav Sharma"));
    await act(async () => { await fireEvent.press(screen.getByTestId("child-switcher-button")); });
    await act(async () => { await fireEvent.press(screen.getByTestId("child-option-k2")); });
    await waitFor(() => expect(screen.getByTestId("selected-child-name").props.children).toBe("Diya Sharma"));
  });
});
