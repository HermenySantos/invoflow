import { pathToFileURL } from "node:url";

const ON = new Set(["1", "true", "yes", "on"]);

export function missingClerkKeyForProductionBuild(env) {
  const source = env ?? process.env;
  const key = String(source.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "").trim();
  const demo = ON.has(String(source.NEXT_PUBLIC_DEMO_AUTH ?? "").trim().toLowerCase());
  return key.length === 0 && !demo;
}

function isMain() {
  const entry = process.argv[1];
  return Boolean(entry) && import.meta.url === pathToFileURL(entry).href;
}

if (isMain()) {
  if (missingClerkKeyForProductionBuild()) {
    console.error(
      "Production build requires NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY. " +
        "Set NEXT_PUBLIC_DEMO_AUTH=1 to build the demo sign-in on purpose."
    );
    process.exit(1);
  }
}
