"use client";

import { useEffect, useLayoutEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  clearAuthTokenGetter,
  markAuthPending,
  markAuthReady,
  registerAuthTokenGetter,
  type TokenGetter,
} from "@/lib/api";

// Layout effects run before any page-level passive effects in the same commit,
// so the readiness gate is armed before the first protected request is issued.
// Falls back to useEffect during server rendering to avoid SSR warnings.
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

/**
 * Bridges Clerk's React useAuth token lifecycle into the centralized api.ts HTTP client.
 * - While Clerk initializes, protected requests wait (bounded) for readiness.
 * - Once loaded and signed in, registers Clerk's getToken so every request obtains
 *   a fresh, short-lived session token without storing it in localStorage.
 * - Once loaded and signed out, no getter is registered and protected requests are
 *   refused locally instead of being sent without a Bearer token.
 */
export function AuthTokenBridge() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  useIsomorphicLayoutEffect(() => {
    if (!isLoaded) {
      markAuthPending();
      return undefined;
    }

    if (isSignedIn) {
      const getter: TokenGetter = async () => {
        try {
          return await getToken();
        } catch {
          return null;
        }
      };
      registerAuthTokenGetter(getter);
      markAuthReady();
      // Only clear the getter this effect registered, never a newer one.
      return () => clearAuthTokenGetter(getter);
    }

    registerAuthTokenGetter(null);
    markAuthReady();
    return undefined;
  }, [getToken, isLoaded, isSignedIn]);

  return null;
}
