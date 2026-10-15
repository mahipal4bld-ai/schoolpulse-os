import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, session } from "@/src/api";
import { queryClient } from "@/src/query-client";
import { setBrandColors } from "@/src/theme";
import type { Me, Membership } from "@/src/types";
import { storage } from "@/src/utils/storage";

const TOKEN_KEY = "sp_token";
const SCHOOL_KEY = "sp_school";

type Status = "loading" | "signedOut" | "signedIn";

type AuthCtx = {
  status: Status;
  me: Me | null;
  membership: Membership | null;
  login: (email: string, password: string) => Promise<Me>;
  acceptInvite: (token: string, name: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  selectSchool: (schoolId: string | null) => Promise<void>;
  refresh: () => Promise<void>;
  can: (perm: string) => boolean;
};

const Ctx = createContext<AuthCtx | null>(null);

export function homeRoute(me: Me | null, membership: Membership | null): string {
  if (!me) return "/login";
  if (!membership) {
    if (me.memberships.length > 1) return "/select-school";
    if (me.user.platform_role === "super_admin") return "/platform";
    return "/no-access";
  }
  if (membership.role === "teacher") return "/today";
  if (membership.role === "parent") return "/family";
  return "/command";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [schoolId, setSchoolId] = useState<string | null>(null);

  const membership = useMemo(
    () => me?.memberships.find((m) => m.school_id === schoolId) ?? null,
    [me, schoolId],
  );

  useEffect(() => {
    const b = membership?.school.brand;
    setBrandColors(b?.primary ?? null, b?.secondary ?? null);
  }, [membership]);

  const applyMe = useCallback(async (data: Me, preferred?: string | null) => {
    let sid = preferred && data.memberships.some((m) => m.school_id === preferred) ? preferred : null;
    if (!sid && data.memberships.length === 1) sid = data.memberships[0].school_id;
    session.setSchool(sid);
    setSchoolId(sid);
    setMe(data);
    setStatus("signedIn");
    await storage.setItem(SCHOOL_KEY, sid);
  }, []);

  const clear = useCallback(async () => {
    session.setToken(null);
    session.setSchool(null);
    await storage.secureRemove(TOKEN_KEY);
    await storage.removeItem(SCHOOL_KEY);
    queryClient.clear();
    setMe(null);
    setSchoolId(null);
    setStatus("signedOut");
  }, []);

  useEffect(() => {
    session.onUnauthorized(() => {
      clear();
    });
    (async () => {
      const token = await storage.secureGet(TOKEN_KEY, null);
      if (!token || typeof token !== "string") return setStatus("signedOut");
      session.setToken(token);
      try {
        const data = await api<Me>("/auth/me", { noSchool: true });
        await applyMe(data, (await storage.getItem(SCHOOL_KEY, null)) as string | null);
      } catch (e: any) {
        if (e?.status === 401) await clear();
        else setStatus("signedOut");
      }
    })();
  }, [applyMe, clear]);

  const finishLogin = useCallback(
    async (res: Me & { access_token: string }) => {
      session.setToken(res.access_token);
      await storage.secureSet(TOKEN_KEY, res.access_token);
      queryClient.clear();
      await applyMe(res, null);
      return res;
    },
    [applyMe],
  );

  const value: AuthCtx = {
    status,
    me,
    membership,
    login: async (email, password) =>
      finishLogin(await api("/auth/login", { body: { email, password }, noSchool: true })),
    acceptInvite: async (token, name, password) =>
      finishLogin(await api("/auth/accept-invite", { body: { token, name, password }, noSchool: true })),
    logout: async () => {
      try {
        await api("/auth/logout", { method: "POST", noSchool: true });
      } catch {
        // session may already be invalid; clear locally regardless
      }
      await clear();
    },
    selectSchool: async (sid) => {
      session.setSchool(sid);
      setSchoolId(sid);
      queryClient.clear();
      await storage.setItem(SCHOOL_KEY, sid);
    },
    refresh: async () => {
      const data = await api<Me>("/auth/me", { noSchool: true });
      setMe(data);
    },
    can: (perm) => !!membership?.permissions.includes(perm),
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
