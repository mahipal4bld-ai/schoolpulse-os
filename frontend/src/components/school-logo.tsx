import { Image } from "expo-image";
import React from "react";
import { View } from "react-native";

import { fileUrl } from "@/src/api";
import { Txt } from "@/src/components/ui";
import { fonts, readableOn } from "@/src/theme";
import type { Brand } from "@/src/types";

export function SchoolLogo({ brand, size = 44, testID }: { brand: Partial<Brand> & { primary: string }; size?: number; testID?: string }) {
  const uri = fileUrl(brand.logo_file_id);
  const style = brand.logo_style ?? "circle";
  const shape =
    style === "circle"
      ? { borderRadius: size / 2 }
      : style === "square"
        ? { borderRadius: size * 0.24 }
        : { borderTopLeftRadius: size * 0.18, borderTopRightRadius: size * 0.18, borderBottomLeftRadius: size * 0.5, borderBottomRightRadius: size * 0.5 };
  if (uri) {
    return (
      <View testID={testID} style={[{ width: size, height: size, overflow: "hidden", backgroundColor: "#FFFFFF" }, shape]}>
        <Image source={{ uri }} style={{ width: size, height: size }} contentFit="cover" transition={150} />
      </View>
    );
  }
  return (
    <View
      testID={testID}
      style={[
        { width: size, height: size, backgroundColor: brand.primary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: brand.secondary ?? brand.primary },
        shape,
      ]}
    >
      <Txt style={{ fontSize: size * 0.36, fontFamily: fonts.medium, lineHeight: size * 0.44, letterSpacing: 0.5 }} color={readableOn(brand.primary)}>
        {(brand.monogram || "SP").slice(0, 3)}
      </Txt>
    </View>
  );
}
