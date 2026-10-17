import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

const mockOpen = jest.fn();
jest.mock("@react-native-community/datetimepicker", () => {
  const { View } = jest.requireActual("react-native");
  return { __esModule: true, default: (p: object) => <View {...p} />, DateTimePickerAndroid: { open: (...a: unknown[]) => mockOpen(...a) } };
});
const mockApi = jest.fn(async (..._a: unknown[]) => ({ items: [] }));
jest.mock("@/src/api", () => ({ api: (...a: unknown[]) => mockApi(...a) }));

import { eventFormProblems, EventForm } from "@/src/components/event-form";
import { ToastProvider } from "@/src/components/toast";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
afterAll(() => qc.clear());
const M = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const wrap = (el: React.ReactElement) => render(
  <SafeAreaProvider initialMetrics={M}><QueryClientProvider client={qc}><ToastProvider>{el}</ToastProvider></QueryClientProvider></SafeAreaProvider>,
);
const disabled = (id: string) => !!screen.getByTestId(id).props.accessibilityState?.disabled;
const pickTime = async (id: string, h: number, m: number) => {
  await act(async () => { fireEvent.press(screen.getByTestId(id)); });
  if (!mockOpen.mock.calls.length) throw new Error(`picker not opened for ${id}`);
  const cfg = mockOpen.mock.calls[mockOpen.mock.calls.length - 1][0];
  await act(async () => cfg.onChange({ type: "set" }, new Date(2026, 0, 1, h, m)));
};

describe("event form validation (edit)", () => {
  const os = Platform.OS;
  beforeAll(() => Object.defineProperty(Platform, "OS", { get: () => "android", configurable: true }));
  afterAll(() => Object.defineProperty(Platform, "OS", { get: () => os, configurable: true }));

  it("edit: an invalid existing range disables Save changes", async () => {
    const initial = { id: "e1", kind: "event" as const, title: "PTA", category: "meeting", description: "", start_date: "2026-10-23", end_date: "2026-10-23", start_time: "10:00", end_time: "11:00", location: "", status: "published" as const };
    await wrap(<EventForm visible day="2026-10-23" initial={initial} onClose={() => {}} />);
    await waitFor(() => expect(disabled("event-save-edit")).toBe(false));
    await pickTime("event-end-time-input", 9, 45);
    await waitFor(() => expect(disabled("event-save-edit")).toBe(true));
  });
});
