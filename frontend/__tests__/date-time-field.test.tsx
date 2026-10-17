import React from "react";
import { fireEvent, render, screen } from "@testing-library/react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { Platform } from "react-native";

const mockOpen = jest.fn();
jest.mock("@react-native-community/datetimepicker", () => {
  const { View } = jest.requireActual("react-native");
  const Picker = (p: object) => <View testID="native-picker" {...p} />;
  return { __esModule: true, default: Picker, DateTimePickerAndroid: { open: (...a: unknown[]) => mockOpen(...a) } };
});

import { DateField, TimeField, timeLabel } from "@/src/components/date-time-field";

const M = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const mount = (el: React.ReactElement) => render(<SafeAreaProvider initialMetrics={M}>{el}</SafeAreaProvider>);

describe("date/time fields", () => {
  it("formats IST wall-clock times for humans", () => {
    expect(timeLabel("09:30")).toBe("9:30 am");
    expect(timeLabel("00:05")).toBe("12:05 am");
    expect(timeLabel("12:00")).toBe("12:00 pm");
    expect(timeLabel("23:45")).toBe("11:45 pm");
    expect(timeLabel(null)).toBe("");
  });

  it("android opens the native dialog and emits standard YYYY-MM-DD / HH:MM values", async () => {
    const os = Platform.OS;
    Object.defineProperty(Platform, "OS", { get: () => "android", configurable: true });
    try {
      const onDate = jest.fn();
      const onTime = jest.fn();
      await mount(<><DateField testID="d" label="Start date" value="2026-10-23" onChange={onDate} /><TimeField testID="t" label="Start time" optional value="09:30" onChange={onTime} /></>);
      expect(screen.getByTestId("t").props.accessibilityLabel).toBe("Start time: 9:30 am");
      expect(screen.getByTestId("d").props.accessibilityLabel).toMatch(/^Start date: .*2026/);  // human-readable, not ISO
      fireEvent.press(screen.getByTestId("d"));
      const cfg = mockOpen.mock.calls[0][0];
      expect(cfg.mode).toBe("date");
      expect(cfg.value.getFullYear()).toBe(2026);
      cfg.onChange({ type: "set" }, new Date(2026, 10, 2, 0, 0));
      expect(onDate).toHaveBeenCalledWith("2026-11-02");
      cfg.onChange({ type: "dismissed" }, undefined);
      expect(onDate).toHaveBeenCalledTimes(1);
      fireEvent.press(screen.getByTestId("t"));
      const t = mockOpen.mock.calls[1][0];
      expect(t.mode).toBe("time");
      t.onChange({ type: "set" }, new Date(2026, 0, 1, 14, 5));
      expect(onTime).toHaveBeenCalledWith("14:05");
      fireEvent.press(screen.getByTestId("t-clear"));
      expect(onTime).toHaveBeenLastCalledWith("");
    } finally {
      Object.defineProperty(Platform, "OS", { get: () => os, configurable: true });
    }
  });
});
