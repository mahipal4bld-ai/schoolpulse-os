import { Redirect } from "expo-router";

import { homeRoute, useAuth } from "@/src/auth";
import { LoadingState } from "@/src/components/ui";

export default function Index() {
  const { status, me, membership } = useAuth();
  if (status === "loading") return <LoadingState testID="app-boot-loading" />;
  if (status === "signedOut") return <Redirect href="/login" />;
  return <Redirect href={homeRoute(me, membership) as any} />;
}
