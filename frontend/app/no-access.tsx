import { useRouter } from "expo-router";
import { LockKey } from "phosphor-react-native";
import React from "react";
import { View } from "react-native";

import { useAuth } from "@/src/auth";
import { Button, EmptyState } from "@/src/components/ui";
import { useTheme } from "@/src/theme";

export default function NoAccess() {
  const { logout } = useAuth();
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <EmptyState
        testID="no-access-state"
        icon={<LockKey size={44} color={colors.muted} />}
        title="No school access yet"
        message="Your account is not linked to any school. Ask your school administrator for an invitation."
        action={
          <Button
            testID="no-access-sign-out"
            variant="outline"
            title="Sign out"
            onPress={async () => {
              await logout();
              router.replace("/login");
            }}
          />
        }
      />
    </View>
  );
}
