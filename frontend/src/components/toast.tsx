import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { View } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

type Tone = "success" | "error" | "info";
type ToastState = { id: number; message: string; tone: Tone } | null;

const ToastCtx = createContext<{ show: (message: string, tone?: Tone) => void }>({ show: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();

  const show = useCallback((message: string, tone: Tone = "success") => {
    if (timer.current) clearTimeout(timer.current);
    Haptics.notificationAsync(
      tone === "error" ? Haptics.NotificationFeedbackType.Error : Haptics.NotificationFeedbackType.Success,
    ).catch(() => {});
    setToast({ id: Date.now(), message, tone });
    timer.current = setTimeout(() => setToast(null), 3200);
  }, []);

  const bg = toast?.tone === "error" ? colors.error : toast?.tone === "info" ? colors.surfaceInverse : colors.surfaceInverse;

  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      {toast ? (
        <Animated.View
          key={toast.id}
          entering={FadeInUp}
          exiting={FadeOutUp}
          style={{ pointerEvents: "none", position: "absolute", top: insets.top + spacing.sm, left: spacing.lg, right: spacing.lg }}
        >
          <View
            testID={`toast-${toast.tone}`}
            style={{ backgroundColor: bg, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.lg }}
          >
            <Txt variant="label" color={colors.onSurfaceInverse}>
              {toast.message}
            </Txt>
          </View>
        </Animated.View>
      ) : null}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
