import { SunHorizon, Chalkboard, UserCircle } from "phosphor-react-native";

import { RoleTabs } from "@/src/components/role-tabs";
import { useI18n } from "@/src/i18n";

export default function TeacherLayout() {
  const { t } = useI18n();
  return (
    <RoleTabs
      allow={(r) => r === "teacher"}
      tabs={[
        { name: "today", label: t("today"), sf: "sun.max.fill", icon: ({ color, size, focused }) => <SunHorizon color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "classes", label: t("classes"), sf: "rectangle.stack.fill", icon: ({ color, size, focused }) => <Chalkboard color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "teacher-profile", label: t("profile"), sf: "person.crop.circle.fill", icon: ({ color, size, focused }) => <UserCircle color={color} size={size} weight={focused ? "fill" : "regular"} /> },
      ]}
    />
  );
}
