import DateTimePicker, { DateTimePickerAndroid, DateTimePickerEvent } from "@react-native-community/datetimepicker";
import { addMonths, format, startOfMonth } from "date-fns";
import { CalendarBlank, Clock, X } from "phosphor-react-native";
import React, { useState } from "react";
import { Platform, Pressable, ScrollView, View } from "react-native";

import { MonthGrid } from "@/src/components/calendar";
import { Sheet } from "@/src/components/sheet";
import { Button, Field, Txt } from "@/src/components/ui";
import { formatDate } from "@/src/format";
import { radius, spacing, useTheme } from "@/src/theme";

/**
 * School dates/times are wall-clock values in Asia/Kolkata ("YYYY-MM-DD", "HH:MM"); the backend interprets them as IST.
 * Native pickers work on local Date objects, so we only ever read/write the wall-clock parts (no UTC shifting).
 */
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const toDate = (d?: string, t?: string) => {
  const [y, m, day] = (d || format(new Date(), "yyyy-MM-dd")).split("-").map(Number);
  const [h, mi] = (t && HHMM.test(t) ? t : "09:00").split(":").map(Number);
  return new Date(y, m - 1, day, h, mi);
};
export const timeLabel = (t?: string | null) => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};
const TIMES = Array.from({ length: 64 }, (_, i) => { const mins = 6 * 60 + i * 15; return `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`; });

function Trigger({ label, text, placeholder, icon, onPress, onClear, testID, error }: { label: string; text: string; placeholder: string; icon: React.ReactNode; onPress: () => void; onClear?: () => void; testID: string; error?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: spacing.xs + 2 }}>
      <Txt variant="label" color={colors.onSurfaceTertiary}>{label}</Txt>
      <Pressable testID={testID} accessibilityRole="button" accessibilityLabel={`${label}: ${text || placeholder}`} onPress={onPress}
        style={{ minHeight: 48, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: error ? colors.error : colors.border, backgroundColor: colors.surface }}>
        {icon}
        <Txt variant="body" raw={!!text} color={text ? colors.onSurface : colors.muted} style={{ flex: 1 }} testID={`${testID}-value`}>{text || placeholder}</Txt>
        {text && onClear ? <Pressable testID={`${testID}-clear`} accessibilityLabel="Clear" hitSlop={10} onPress={onClear}><X size={16} color={colors.muted} /></Pressable> : null}
      </Pressable>
      {error ? <Txt variant="caption" raw color={colors.error}>{error}</Txt> : null}
    </View>
  );
}

function IosSheet({ visible, mode, value, onDone, onClose, min }: { visible: boolean; mode: "date" | "time"; value: Date; onDone: (d: Date) => void; onClose: () => void; min?: Date }) {
  const [d, setD] = useState(value);
  React.useEffect(() => { if (visible) setD(value); }, [visible]);  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Sheet visible={visible} onClose={onClose} title={mode === "date" ? "Select date" : "Select time"} footer={<Button testID="picker-done" title="Done" onPress={() => onDone(d)} />}>
      <DateTimePicker value={d} mode={mode} display={mode === "date" ? "inline" : "spinner"} minimumDate={min} minuteInterval={5} onChange={(_e, v) => v && setD(v)} />
    </Sheet>
  );
}

export function DateField({ label, value, onChange, min, testID, optional, error }: { label: string; value: string; onChange: (v: string) => void; min?: string; testID: string; optional?: boolean; error?: string }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => startOfMonth(toDate(value || min)));
  const show = () => {
    if (Platform.OS === "android") {
      DateTimePickerAndroid.open({ value: toDate(value || min), mode: "date", minimumDate: min ? toDate(min) : undefined, onChange: (e: DateTimePickerEvent, d?: Date) => { if (e.type === "set" && d) onChange(format(d, "yyyy-MM-dd")); } });
    } else { setMonth(startOfMonth(toDate(value || min))); setOpen(true); }
  };
  return (
    <>
      <Trigger testID={testID} label={label} text={value ? formatDate(value) : ""} placeholder={optional ? "Optional" : "Select date"} error={error} icon={<CalendarBlank size={18} color={colors.onSurfaceTertiary} />} onPress={show} onClear={optional ? () => onChange("") : undefined} />
      {Platform.OS === "ios" ? <IosSheet visible={open} mode="date" value={toDate(value || min)} min={min ? toDate(min) : undefined} onClose={() => setOpen(false)} onDone={(d) => { onChange(format(d, "yyyy-MM-dd")); setOpen(false); }} /> : null}
      {Platform.OS === "web" ? (
        <Sheet visible={open} onClose={() => setOpen(false)} title="Select date" testID={`${testID}-sheet`}>
          <MonthGrid month={month} items={[]} selected={value || null} minDate={min} onMonth={(n) => setMonth(addMonths(month, n))} onSelect={(d) => { if (d) { onChange(d); setOpen(false); } }} />
        </Sheet>
      ) : null}
    </>
  );
}

export function TimeField({ label, value, onChange, testID, optional, error }: { label: string; value: string; onChange: (v: string) => void; testID: string; optional?: boolean; error?: string }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const show = () => {
    if (Platform.OS === "android") {
      DateTimePickerAndroid.open({ value: toDate(undefined, value), mode: "time", is24Hour: false, onChange: (e: DateTimePickerEvent, d?: Date) => { if (e.type === "set" && d) onChange(format(d, "HH:mm")); } });
    } else { setTyped(value); setOpen(true); }
  };
  const valid = HHMM.test(typed);
  return (
    <>
      <Trigger testID={testID} label={label} text={timeLabel(value)} placeholder={optional ? "Optional" : "Select time"} error={error} icon={<Clock size={18} color={colors.onSurfaceTertiary} />} onPress={show} onClear={optional ? () => onChange("") : undefined} />
      {Platform.OS === "ios" ? <IosSheet visible={open} mode="time" value={toDate(undefined, value)} onClose={() => setOpen(false)} onDone={(d) => { onChange(format(d, "HH:mm")); setOpen(false); }} /> : null}
      {Platform.OS === "web" ? (
        <Sheet visible={open} onClose={() => setOpen(false)} title="Select time" testID={`${testID}-sheet`} footer={
          <Button testID={`${testID}-apply`} title="Use typed time" disabled={!valid} onPress={() => { onChange(typed); setOpen(false); }} />
        }>
          <ScrollView style={{ maxHeight: 260 }} contentContainerStyle={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {TIMES.map((t) => <Button key={t} small variant={t === value ? "primary" : "outline"} testID={`${testID}-opt-${t.replace(":", "")}`} title={timeLabel(t)} onPress={() => { onChange(t); setOpen(false); }} />)}
          </ScrollView>
          <Field testID={`${testID}-typed`} label="Or type a time (24-hour HH:MM)" value={typed} onChangeText={setTyped} autoCapitalize="none" placeholder="e.g. 14:05" error={typed && !valid ? "Use HH:MM, e.g. 09:30" : undefined} />
        </Sheet>
      ) : null}
    </>
  );
}
