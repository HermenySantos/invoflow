import { describe, expect, it } from "vitest";
import { missingClerkKeyForProductionBuild } from "../../scripts/require-clerk-key.mjs";

describe("missingClerkKeyForProductionBuild", () => {
  it("blocks a production build that has neither a Clerk key nor an explicit demo flag", () => {
    expect(missingClerkKeyForProductionBuild({})).toBe(true);
    expect(missingClerkKeyForProductionBuild({ NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "  " })).toBe(true);
    expect(missingClerkKeyForProductionBuild({ NEXT_PUBLIC_DEMO_AUTH: "0" })).toBe(true);
  });

  it("allows a key, or an explicit demo flag", () => {
    expect(
      missingClerkKeyForProductionBuild({ NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk_live_x" })
    ).toBe(false);
    expect(missingClerkKeyForProductionBuild({ NEXT_PUBLIC_DEMO_AUTH: "1" })).toBe(false);
    expect(missingClerkKeyForProductionBuild({ NEXT_PUBLIC_DEMO_AUTH: "true" })).toBe(false);
  });
});
