import { useLocalSearchParams } from "expo-router";
import React from "react";

import { useAuth } from "@/src/auth";
import { WeeklyTimetable } from "@/src/components/timetable";

export default function ChildTimetable() {
  const { studentId, name } = useLocalSearchParams<{ studentId: string; name?: string }>();
  const { membership } = useAuth();
  return <WeeklyTimetable path={`/parent/children/${studentId}/timetable`} queryKey={["parent-tt", membership?.school_id, studentId]} title="Timetable" subtitle={name} show="none" />;
}
