/**
 * Module resolution hooks for the plain-Node diagnostic worker.
 *
 * Maps "@/..." to frontend/src/... and retries TypeScript extension
 * candidates for extensionless relative imports (".js" is required for
 * next/server's own internals). Node's native TypeScript type stripping
 * handles erasable syntax; no bundler, no tsx, no extra flags.
 */

import { existsSync, statSync } from "node:fs";
import { registerHooks } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC_ROOT = path.join(FRONTEND_ROOT, "src");

const SUFFIXES = [".ts", ".tsx", ".js", "/index.ts", "/index.tsx", "/index.js"];

function firstExistingFile(base) {
  for (const suffix of SUFFIXES) {
    const candidate = `${base}${suffix}`;
    if (existsSync(candidate) && statSync(candidate).isFile()) {
      return pathToFileURL(candidate).href;
    }
  }
  return null;
}

export function installDiagnosticResolveHooks() {
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (specifier.startsWith("@/")) {
        const resolved = firstExistingFile(path.join(SRC_ROOT, specifier.slice(2)));
        if (resolved) return { url: resolved, shortCircuit: true };
        throw new Error(`diagnostic resolve hook: cannot resolve ${specifier}`);
      }
      if (
        (specifier.startsWith("./") || specifier.startsWith("../")) &&
        context.parentURL?.startsWith(pathToFileURL(SRC_ROOT).href)
      ) {
        const parentDir = path.dirname(fileURLToPath(context.parentURL));
        const resolved = firstExistingFile(path.resolve(parentDir, specifier));
        if (resolved) return { url: resolved, shortCircuit: true };
      }
      try {
        return nextResolve(specifier, context);
      } catch (error) {
        // Some shipped entries (e.g. next/server in Next 16) are missing
        // from the package exports map while the file exists; the ".js"
        // retry over node_modules resolves them.
        const resolved = firstExistingFile(
          path.join(FRONTEND_ROOT, "node_modules", specifier),
        );
        if (resolved) return { url: resolved, shortCircuit: true };
        throw error;
      }
    },
  });
}
