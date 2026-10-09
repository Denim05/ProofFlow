"use client";

import { useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { registerAuthTokenGetter } from "@/lib/api";

/**
 * Bridges Clerk's React useAuth token lifecycle into the centralized api.ts HTTP client.
 * Registers Clerk's getToken getter so every outgoing fetch and XHR request
 * obtains a fresh, short-lived session token without storing it in localStorage.
 */
export function AuthTokenBridge() {
  const { getToken, isSignedIn } = useAuth();

  useEffect(() => {
    if (isSignedIn) {
      registerAuthTokenGetter(async () => {
        try {
          return await getToken();
        } catch {
          return null;
        }
      });
    } else {
      registerAuthTokenGetter(null);
    }

    return () => {
      registerAuthTokenGetter(null);
    };
  }, [getToken, isSignedIn]);

  return null;
}
