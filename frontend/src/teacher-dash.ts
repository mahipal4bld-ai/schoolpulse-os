import { useQuery } from "@tanstack/react-query";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";

export type TeacherDash = {
  teacher: { name: string; designation: string } | null;
  total_students: number;
  sections: { section_id: string; label: string; subjects: string[]; is_class_teacher: boolean; students: number }[];
};

export function useTeacherDash() {
  const { membership } = useAuth();
  return useQuery({ queryKey: ["teacher-dash", membership?.school_id], queryFn: () => api<TeacherDash>("/teacher/dashboard") });
}

