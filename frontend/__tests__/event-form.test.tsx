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
  const cfg = mockOpen.mock.calls[mockOpen.mock.calls.length - 1][0];
  await act(async () => cfg.onChange({ type: "set" }, new Date(2026, 0, 1, h, m)));
};

describe("event form validation", () => {
  const os = Platform.OS;
  beforeAll(() => Object.defineProperty(Platform, "OS", { get: () => "android", configurable: true }));
  afterAll(() => Object.defineProperty(Platform, "OS", { get: () => os, configurable: true }));

  it("rules mirror the server", () => {
    const ok = { start: "2026-10-23", end: "", startTime: "", endTime: "" };
    expect(eventFormProblems(ok)).toEqual({});
    expect(eventFormProblems({ ...ok, end: "2026-10-22" }).end).toBeTruthy();
    expect(eventFormProblems({ ...ok, endTime: "09:00" }).startTime).toBeTruthy();
    expect(eventFormProblems({ ...ok, startTime: "10:00", endTime: "09:00" }).endTime).toBeTruthy();
    expect(eventFormProblems({ ...ok, startTime: "10:00", endTime: "10:00" }).endTime).toBeTruthy();
    expect(eventFormProblems({ ...ok, end: "2026-10-24", startTime: "10:00", endTime: "09:00" })).toEqual({});  // multi-day
  });

  it("create: end time before start time disables Save draft and Publish; fixing it re-enables both", async () => {
    await wrap(<EventForm visible day="2026-10-23" onClose={() => {}} />);
    fireEvent.changeText(screen.getByTestId("event-title-input"), "Sports day");
    await waitFor(() => expect(disabled("event-publish")).toBe(false));
    await pickTime("event-start-time-input", 10, 0);
    await pickTime("event-end-time-input", 9, 0);
    await waitFor(() => expect(disabled("event-publish")).toBe(true));
    await waitFor(() => expect(disabled("event-save-draft")).toBe(true));
    fireEvent.press(screen.getByTestId("event-publish"));
    expect(mockApi).not.toHaveBeenCalledWith("/events", expect.anything());
    await pickTime("event-end-time-input", 11, 30);
    await waitFor(() => expect(disabled("event-publish")).toBe(false));
    await waitFor(() => expect(disabled("event-save-draft")).toBe(false));
  });
});
