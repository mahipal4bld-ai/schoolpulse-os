import { House, BellSimple, UserCircle } from "phosphor-react-native";

import { RoleTabs } from "@/src/components/role-tabs";
import { useI18n } from "@/src/i18n";

export default function ParentLayout() {
  const { t } = useI18n();
  return (
    <RoleTabs
      allow={(r) => r === "parent"}
      tabs={[
        { name: "family", label: t("home"), sf: "house.fill", icon: ({ color, size, focused }) => <House color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "updates", label: t("updates"), sf: "bell.fill", icon: ({ color, size, focused }) => <BellSimple color={color} size={size} weight={focused ? "fill" : "regular"} /> },
        { name: "parent-profile", label: t("profile"), sf: "person.crop.circle.fill", icon: ({ color, size, focused }) => <UserCircle color={color} size={size} weight={focused ? "fill" : "regular"} /> },
      ]}
    />
  );
}
