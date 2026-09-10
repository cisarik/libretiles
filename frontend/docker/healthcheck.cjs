"use strict";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const http = require("node:http");

const request = http.get(
  { hostname: "127.0.0.1", port: 3000, path: "/", timeout: 3000 },
  (response) => {
    response.resume();
    process.exit(response.statusCode && response.statusCode < 500 ? 0 : 1);
  },
);
request.on("timeout", () => request.destroy());
request.on("error", () => process.exit(1));
