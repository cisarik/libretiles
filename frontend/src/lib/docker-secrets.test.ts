import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { afterEach, describe, expect, it } from "vitest";

const roots: string[] = [];
const loader = join(process.cwd(), "docker", "load-secrets.cjs");

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function fixture(contents: string): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "libretiles-docker-secrets-"));
  roots.push(root);
  const path = join(root, "credentials.json");
  await writeFile(path, contents, { mode: 0o600 });
  await chmod(path, 0o600);
  return path;
}

function run(path: string, extraEnv: Record<string, string> = {}) {
  const env: NodeJS.ProcessEnv = {
    NODE_ENV: "test",
    PATH: process.env.PATH,
    LIBRETILES_FRONTEND_SECRETS_FILE: path,
    ...extraEnv,
  };
  return spawnSync(process.execPath, ["--require", loader, "-e", "process.stdout.write(process.env.OPENROUTER_API_KEY || 'missing')"], {
    encoding: "utf8",
    env,
  });
}

describe("Docker frontend secret preload", () => {
  it("loads only closed, non-placeholder values without logging them", async () => {
    const path = await fixture(JSON.stringify({ OPENROUTER_API_KEY: "synthetic-test-value-123456" }));
    const result = run(path);
    expect(result.status).toBe(0);
    expect(result.stdout).toBe("synthetic-test-value-123456");
    expect(result.stderr).toBe("");
  });

  it("rejects unknown names, placeholders, and direct-value conflicts", async () => {
    const unknown = run(await fixture(JSON.stringify({ UNKNOWN_KEY: "synthetic-value" })));
    expect(unknown.status).not.toBe(0);

    const placeholder = run(await fixture(JSON.stringify({ OPENROUTER_API_KEY: "replace-me" })));
    expect(placeholder.status).not.toBe(0);

    const conflictPath = await fixture(JSON.stringify({ OPENROUTER_API_KEY: "synthetic-file-value" }));
    const conflict = run(conflictPath, { OPENROUTER_API_KEY: "synthetic-direct-value" });
    expect(conflict.status).not.toBe(0);
  });
});
