"use strict";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require("node:fs");

const SECRET_FILE_ENV = "LIBRETILES_FRONTEND_SECRETS_FILE";
const MAX_FILE_BYTES = 64 * 1024;
const MAX_VALUE_BYTES = 8 * 1024;
const ALLOWED_NAMES = new Set([
  "GROQ_API_KEY",
  "GEMINI_API_KEY",
  "CLOUDFLARE_API_TOKEN",
  "CLOUDFLARE_ACCOUNT_ID",
  "MISTRAL_API_KEY",
  "IBM_CLOUD_API_KEY",
  "IBM_WATSONX_PROJECT_ID",
  "IBM_WATSONX_REGION",
  "AION_API_KEY",
  "HF_TOKEN",
  "OPENROUTER_API_KEY",
  "NVIDIA_API_KEY",
]);

function fail(message) {
  throw new Error(`frontend secret configuration error: ${message}`);
}

const path = process.env[SECRET_FILE_ENV];
if (path) {
  if (!path.startsWith("/")) fail("secret path must be absolute");
  const stat = fs.lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink()) fail("secret path must be a regular file");
  if (stat.size < 2 || stat.size > MAX_FILE_BYTES) fail("secret file size is invalid");
  if ((stat.mode & 0o022) !== 0) fail("secret file must not be group/other writable");

  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(path, "utf8"));
  } catch {
    fail("secret file must contain valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    fail("secret file must contain one JSON object");
  }
  for (const [name, value] of Object.entries(parsed)) {
    if (!ALLOWED_NAMES.has(name)) fail(`unsupported key ${name}`);
    if (process.env[name] !== undefined) fail(`conflicting direct value for ${name}`);
    if (typeof value !== "string" || value.length === 0 || value.length > MAX_VALUE_BYTES) {
      fail(`invalid value for ${name}`);
    }
    if (value !== value.trim() || /[\0\r\n]/.test(value)) fail(`invalid value for ${name}`);
    const normalized = value.toLowerCase();
    if (normalized.startsWith("your-") || normalized.includes("replace-me") || normalized.includes("placeholder")) {
      fail(`placeholder value for ${name}`);
    }
    process.env[name] = value;
  }
}
