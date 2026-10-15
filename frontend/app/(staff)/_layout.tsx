import { House, UsersThree, Books, GearSix } from "phosphor-react-native";

import { RoleTabs } from "@/src/components/role-tabs";
import { useI18n } from "@/src/i18n";

export default function StaffLayout() {
  const { t } = useI18n();
  return (
    <RoleTabs
      allow={(r) => r !== "teacher" && r !== "parent"}
      tabs={[
        { name: "command", label: t("home"), sf: "house.fill", icon: ({ color, size, focused }) => <House color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "people", label: t("people"), sf: "person.2.fill", icon: ({ color, size, focused }) => <UsersThree color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "academics", label: t("academics"), sf: "books.vertical.fill", icon: ({ color, size, focused }) => <Books color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "settings", label: t("settings"), sf: "gearshape.fill", icon: ({ color, size, focused }) => <GearSix color={color} size={size} weight={focused ? "fill" : "regular"} /> },
      ]}
    />
  );
}
