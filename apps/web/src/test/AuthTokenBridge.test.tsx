import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render } from "@testing-library/react";
import { api, resetAuthStateForTests } from "@/lib/api";
import { AuthTokenBridge } from "@/components/AuthTokenBridge";

const clerkState = {
  isLoaded: false,
  isSignedIn: undefined as boolean | undefined,
  getToken: vi.fn(async () => "bridge_session_token" as string | null),
};

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => clerkState,
}));

function mockFetch() {
  const calls: Headers[] = [];
  const fn = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
    calls.push(init?.headers as Headers);
    return Promise.resolve({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: () =>
        Promise.resolve({
          success: true,
          data: { items: [], pagination: { page: 1, limit: 10, total: 0, pages: 0 } },
        }),
    });
  });
  global.fetch = fn as unknown as typeof fetch;
  return { fn, calls };
}

describe("AuthTokenBridge", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    resetAuthStateForTests();
    clerkState.isLoaded = false;
    clerkState.isSignedIn = undefined;
    clerkState.getToken = vi.fn(async () => "bridge_session_token");
  });

  afterEach(() => {
    global.fetch = originalFetch;
    resetAuthStateForTests();
  });

  it("holds protected requests while Clerk loads, then sends them with the session token", async () => {
    const { fn, calls } = mockFetch();
    const { rerender } = render(<AuthTokenBridge />);

    const pending = api.listCases();
    await Promise.resolve();
    await Promise.resolve();
    expect(fn).not.toHaveBeenCalled();

    clerkState.isLoaded = true;
    clerkState.isSignedIn = true;
    rerender(<AuthTokenBridge />);
    await pending;

    expect(fn).toHaveBeenCalledTimes(1);
    expect(calls[0].get("Authorization")).toBe("Bearer bridge_session_token");
    expect(calls[0].get("X-User-ID")).toBeNull();
  });

  it("refuses protected requests for a loaded, signed-out session", async () => {
    clerkState.isLoaded = true;
    clerkState.isSignedIn = false;
    const { fn } = mockFetch();
    render(<AuthTokenBridge />);

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
    expect(clerkState.getToken).not.toHaveBeenCalled();
  });

  it("removes the token getter after sign-out", async () => {
    clerkState.isLoaded = true;
    clerkState.isSignedIn = true;
    const { fn } = mockFetch();
    const { rerender } = render(<AuthTokenBridge />);
    await api.listCases();
    expect(fn).toHaveBeenCalledTimes(1);

    clerkState.isSignedIn = false;
    rerender(<AuthTokenBridge />);

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("clears its token getter on unmount", async () => {
    clerkState.isLoaded = true;
    clerkState.isSignedIn = true;
    const { fn } = mockFetch();
    const { unmount } = render(<AuthTokenBridge />);
    unmount();

    await expect(api.listCases()).rejects.toMatchObject({ status: 401, code: "AUTH_REQUIRED" });
    expect(fn).not.toHaveBeenCalled();
  });
});
