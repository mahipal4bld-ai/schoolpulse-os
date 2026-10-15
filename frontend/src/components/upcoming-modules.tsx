import React from "react";

import { Card, ComingSoonRow, SectionTitle } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import type { Role } from "@/src/types";

const MODULES: Record<string, [string, string][]> = {
  parent: [
    ["Attendance", "Daily presence and monthly summary"],
    ["Homework & diary", "Assignments and class updates"],
    ["Fees", "Dues, receipts and online payment"],
    ["Calendar & timetable", "Holidays, events and periods"],
    ["Messages", "Notices and teacher communication"],
  ],
  teacher: [
    ["Attendance marking", "One-tap daily attendance per section"],
    ["Homework", "Assign work and track submissions"],
    ["Examinations", "Marks entry and report cards"],
    ["AI Teacher Assistant", "Drafts grounded in your class data"],
  ],
  staff: [
    ["Fees & receipts", "Structures, collections and reconciliation"],
    ["Admissions CRM", "Enquiries and conversion tracking"],
    ["Attendance analytics", "Student and staff attendance trends"],
    ["Notices & communication", "Approved broadcasts to parents"],
    ["AI Owner Briefing", "Daily fact-grounded management summary"],
    ["Transport & pickup", "Routes and authorised pickup"],
  ],
};

export function UpcomingModules({ role }: { role: Role }) {
  const { t } = useI18n();
  const key = role === "parent" ? "parent" : role === "teacher" ? "teacher" : "staff";
  const list = MODULES[key];
  return (
    <>
      <SectionTitle title={t("upcomingModules")} />
      <Card style={{ paddingVertical: 0 }} testID="upcoming-modules-card">
        {list.map(([title, sub], i) => (
          <ComingSoonRow key={title} title={title} subtitle={sub} last={i === list.length - 1} />
        ))}
      </Card>
    </>
  );
}
