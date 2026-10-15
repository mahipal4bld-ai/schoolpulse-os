import { QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { LogBox, View } from "react-native";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { AuthProvider } from "@/src/auth";
import { ErrorBoundary } from "@/src/components/error-boundary";
import { ToastProvider } from "@/src/components/toast";
import { loadLang } from "@/src/i18n";
import { queryClient } from "@/src/query-client";
import { useTheme } from "@/src/theme";

// Disable logbox errors etc so that users can see the app
// and agent works as expected.
LogBox.ignoreAllLogs(true);

export default function RootLayout() {
  const { colors } = useTheme();
  const [loaded] = useFonts({
    "Jakarta-400": require("../assets/fonts/PlusJakartaSans-400.ttf"),
    "Jakarta-500": require("../assets/fonts/PlusJakartaSans-500.ttf"),
    "Jakarta-600": require("../assets/fonts/PlusJakartaSans-600.ttf"),
  });
  useEffect(() => {
    loadLang();
  }, []);

  if (!loaded) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  // One app level ErrorBoundary; a render crash shows a reload screen
  // instead of a blank app.
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <KeyboardProvider>
          <AuthProvider>
            <ToastProvider>
              <StatusBar style="dark" />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surfaceSecondary } }} />
            </ToastProvider>
          </AuthProvider>
        </KeyboardProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
