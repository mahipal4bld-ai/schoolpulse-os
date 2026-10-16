import React from "react";

import { useAuth } from "@/src/auth";
import { WeeklyTimetable } from "@/src/components/timetable";

export default function MyTimetable() {
  const { membership } = useAuth();
  return <WeeklyTimetable path="/timetable/teacher/me" queryKey={["my-timetable", membership?.school_id]} title="My timetable" show="section" />;
}
