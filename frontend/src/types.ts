export type Role =
  | "owner"
  | "principal"
  | "school_admin"
  | "accountant"
  | "admission_coordinator"
  | "teacher"
  | "transport_coordinator"
  | "parent";

export type Brand = {
  primary: string;
  secondary: string;
  logo_file_id?: string | null;
  banner_file_id?: string | null;
  monogram: string;
  logo_style: "circle" | "shield" | "square";
  welcome_message?: string;
};

export type School = {
  id: string;
  name: string;
  slug: string;
  status: string;
  tagline?: string;
  description?: string;
  brand: Brand;
  contact: Record<string, string>;
  academic_session_label?: string;
  preferred_language?: "en" | "hi";
  board?: string;
  operating?: { start_time: string; end_time: string; working_days: string };
  custom_domain?: string;
  photos?: string[];
  plan?: string;
};

export type Membership = { school_id: string; role: Role; permissions: string[]; school: School };

export type Me = {
  user: { id: string; email: string; name: string; phone?: string; platform_role?: string | null; preferred_language?: string };
  memberships: Membership[];
};

export type Student = {
  id: string;
  admission_no: string;
  first_name: string;
  last_name: string;
  gender: string;
  dob: string;
  class_name: string;
  section_name: string;
  section_id: string;
  class_id: string;
  roll_no?: number;
  status: string;
  relation?: string;
};

export type Teacher = {
  id: string;
  name: string;
  email: string;
  phone: string;
  designation: string;
  employee_code?: string;
  status: string;
  user_id?: string | null;
  assignments: {
    id: string;
    section_id: string;
    section_label: string;
    subject_name?: string | null;
    is_class_teacher: boolean;
  }[];
};

export type Section = { id: string; name: string; class_id: string; class_name: string; capacity: number };
export type SchoolClass = {
  id: string;
  name: string;
  order: number;
  academic_year_id: string;
  sections: Section[];
  student_count: number;
};
