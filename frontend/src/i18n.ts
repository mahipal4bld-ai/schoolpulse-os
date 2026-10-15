// Lightweight i18n: English + Hindi. Add keys to both dictionaries.
import { useSyncExternalStore } from "react";

import { hi as hiCatalog, hiPatterns } from "@/src/i18n-hi";
import { storage } from "@/src/utils/storage";

const en = {
  signIn: "Sign in",
  email: "Email",
  password: "Password",
  welcomeBack: "Welcome back",
  signInSubtitle: "Sign in to your school's SchoolPulse account",
  useDemo: "Use a demo account",
  haveInvite: "Have an invitation code?",
  home: "Home",
  people: "People",
  academics: "Academics",
  settings: "Settings",
  today: "Today",
  classes: "Classes",
  profile: "Profile",
  updates: "Updates",
  goodMorning: "Good morning",
  goodAfternoon: "Good afternoon",
  goodEvening: "Good evening",
  students: "Students",
  teachers: "Teachers",
  guardians: "Guardians",
  staff: "Staff",
  sections: "Sections",
  subjects: "Subjects",
  academicYears: "Academic years",
  brandStudio: "Brand Studio",
  schoolProfile: "School profile",
  invitations: "Staff invitations",
  auditLog: "Audit log",
  importCsv: "Import students (CSV)",
  language: "Language",
  signOut: "Sign out",
  switchSchool: "Switch school",
  comingSoon: "Coming soon",
  upcomingModules: "Upcoming modules",
  search: "Search",
  save: "Save changes",
  myChildren: "My children",
  classTeacher: "Class teacher",
  roster: "Roster",
  assignedClasses: "Assigned classes",
  recentActivity: "Recent activity",
  commandCentre: "Command Centre",
  schoolOverview: "School overview",
  quickActions: "Quick actions",
  studentsByClass: "Students by class",
  liveFromRecords: "Live from records",
  addStudent: "Add a student",
  academicSetup: "Academic setup",
  directory: "Student & staff directory",
  school: "School",
};

const hi: typeof en = {
  signIn: "साइन इन करें",
  email: "ईमेल",
  password: "पासवर्ड",
  welcomeBack: "फिर से स्वागत है",
  signInSubtitle: "अपने स्कूल के SchoolPulse खाते में साइन इन करें",
  useDemo: "डेमो खाता उपयोग करें",
  haveInvite: "क्या आपके पास आमंत्रण कोड है?",
  home: "होम",
  people: "लोग",
  academics: "शैक्षणिक",
  settings: "सेटिंग्स",
  today: "आज",
  classes: "कक्षाएँ",
  profile: "प्रोफ़ाइल",
  updates: "अपडेट",
  goodMorning: "सुप्रभात",
  goodAfternoon: "नमस्कार",
  goodEvening: "शुभ संध्या",
  students: "विद्यार्थी",
  teachers: "शिक्षक",
  guardians: "अभिभावक",
  staff: "स्टाफ़",
  sections: "सेक्शन",
  subjects: "विषय",
  academicYears: "शैक्षणिक वर्ष",
  brandStudio: "ब्रांड स्टूडियो",
  schoolProfile: "स्कूल प्रोफ़ाइल",
  invitations: "स्टाफ़ आमंत्रण",
  auditLog: "ऑडिट लॉग",
  importCsv: "विद्यार्थी आयात (CSV)",
  language: "भाषा",
  signOut: "साइन आउट",
  switchSchool: "स्कूल बदलें",
  comingSoon: "जल्द आ रहा है",
  upcomingModules: "आगामी मॉड्यूल",
  search: "खोजें",
  save: "बदलाव सहेजें",
  myChildren: "मेरे बच्चे",
  classTeacher: "कक्षा शिक्षक",
  roster: "सूची",
  assignedClasses: "आवंटित कक्षाएँ",
  recentActivity: "हाल की गतिविधि",
  commandCentre: "कमांड सेंटर",
  schoolOverview: "स्कूल अवलोकन",
  quickActions: "त्वरित कार्य",
  studentsByClass: "कक्षा अनुसार विद्यार्थी",
  liveFromRecords: "रिकॉर्ड से लाइव",
  addStudent: "विद्यार्थी जोड़ें",
  academicSetup: "शैक्षणिक सेटअप",
  directory: "विद्यार्थी व स्टाफ़ निर्देशिका",
  school: "स्कूल",
};

export type Lang = "en" | "hi";
export type TKey = keyof typeof en;
const dicts = { en, hi };

let lang: Lang = "en";
const listeners = new Set<() => void>();
const LANG_KEY = "sp_lang";

export async function loadLang() {
  const saved = (await storage.getItem(LANG_KEY, "en")) as string | null;
  lang = saved === "hi" ? "hi" : "en";
  listeners.forEach((l) => l());
}

export async function setLang(next: Lang) {
  lang = next;
  listeners.forEach((l) => l());
  await storage.setItem(LANG_KEY, next);
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function useI18n() {
  const current = useSyncExternalStore(subscribe, () => lang, () => lang);
  return { lang: current, t: (k: TKey) => dicts[current][k] ?? en[k] };
}

// Translate an English source string. English is the fallback for anything not in the catalogue.
export function translate(language: Lang, text: string): string {
  if (language !== "hi" || !text) return text;
  const key = text.trim();
  const hit = hiCatalog[key];
  if (hit) return text.replace(key, hit);
  for (const [rx, fn] of hiPatterns) {
    const m = key.match(rx);
    if (m) return text.replace(key, fn(m));
  }
  return text;
}

export function useTx() {
  const { lang: current } = useI18n();
  return (text?: string) => (text === undefined ? text : translate(current, text));
}
