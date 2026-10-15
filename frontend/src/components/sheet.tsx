import React from "react";
import { Modal, Platform, Pressable, View } from "react-native";
import { KeyboardAvoidingView, KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { X } from "phosphor-react-native";

import { Txt } from "@/src/components/ui";
import { radius, spacing, useTheme } from "@/src/theme";

export function Sheet({
  visible,
  onClose,
  title,
  children,
  footer,
  testID,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  testID?: string;
}) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose} statusBarTranslucent>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <View style={{ flex: 1, justifyContent: "flex-end" }}>
          <Pressable testID={`${testID ?? "sheet"}-backdrop`} style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, backgroundColor: colors.backdrop }} onPress={onClose} />
          <View
            testID={testID}
            style={{
              backgroundColor: colors.surface,
              borderTopLeftRadius: radius.lg + 4,
              borderTopRightRadius: radius.lg + 4,
              maxHeight: "88%",
              paddingBottom: insets.bottom + spacing.lg,
            }}
          >
            <View style={{ alignItems: "center", paddingTop: spacing.sm }}>
              <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong }} />
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.sm }}>
              <Txt variant="heading" style={{ flex: 1 }}>
                {title}
              </Txt>
              <Pressable testID={`${testID ?? "sheet"}-close`} onPress={onClose} hitSlop={10} style={{ width: 44, height: 44, alignItems: "flex-end", justifyContent: "center" }}>
                <X size={20} color={colors.muted} />
              </Pressable>
            </View>
            <KeyboardAwareScrollView
              bottomOffset={24}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ paddingHorizontal: spacing.xl, paddingBottom: spacing.lg, gap: spacing.lg }}
            >
              {children}
            </KeyboardAwareScrollView>
            {footer ? <View style={{ paddingHorizontal: spacing.xl, paddingTop: spacing.sm }}>{footer}</View> : null}
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
