import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import net from "node:net";

const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const workspace = process.cwd();
const outputDir = join(workspace, "docs", "assets", "product-overall-design");
const baseUrl = process.env.VISUAL_BASE_URL || "http://127.0.0.1:3000";
const profile = mkdtempSync(join(tmpdir(), "lingjing-doc-evidence-"));
const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

const captures = [
  { name: "01-tourist-home", path: "/", ready: ".tourist-shell" },
  { name: "02-admin-overview", path: "/admin", ready: "#admin-panel-overview:not([hidden])" },
  { name: "03-admin-knowledge", path: "/admin", ready: "#admin-panel-knowledge:not([hidden])", click: "#admin-tab-knowledge" },
  { name: "04-admin-quality", path: "/admin", ready: "#admin-panel-quality:not([hidden])", click: "#admin-tab-quality" },
];

function getFreePort() {
  return new Promise((resolvePort, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolvePort(port));
    });
  });
}

async function waitForPage(port) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const pages = await fetch(`http://127.0.0.1:${port}/json/list`).then((response) => response.json());
      const page = pages.find((entry) => entry.type === "page" && entry.webSocketDebuggerUrl);
      if (page) return page;
    } catch {}
    await delay(150);
  }
  throw new Error("Edge DevTools endpoint did not become ready.");
}

async function connectCdp(url) {
  const socket = new WebSocket(url);
  const pending = new Map();
  let requestId = 0;
  await new Promise((resolveOpen, reject) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolveRequest, rejectRequest } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) rejectRequest(new Error(message.error.message));
    else resolveRequest(message.result || {});
  });
  return {
    send(method, params = {}) {
      requestId += 1;
      const id = requestId;
      const response = new Promise((resolveRequest, rejectRequest) => pending.set(id, { resolveRequest, rejectRequest }));
      socket.send(JSON.stringify({ id, method, params }));
      return response;
    },
    close() { socket.close(); },
  };
}

async function waitForSelector(cdp, selector) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    const result = await cdp.send("Runtime.evaluate", {
      expression: `document.readyState === "complete" && Boolean(document.querySelector(${JSON.stringify(selector)}))`,
      returnByValue: true,
    });
    if (result.result?.value === true) {
      await delay(1_800);
      return;
    }
    await delay(200);
  }
  throw new Error(`Page did not become ready for ${selector}.`);
}

const port = await getFreePort();
mkdirSync(outputDir, { recursive: true });
const browser = spawn(edge, [
  "--headless=new",
  "--disable-gpu",
  "--disable-extensions",
  "--disable-background-networking",
  "--disable-sync",
  "--metrics-recording-only",
  "--mute-audio",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: "ignore", windowsHide: true });

let cdp;
try {
  const page = await waitForPage(port);
  cdp = await connectCdp(page.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
    screenWidth: 1440,
    screenHeight: 900,
  });

  for (const capture of captures) {
    await cdp.send("Page.navigate", { url: `${baseUrl}${capture.path}` });
    await waitForSelector(cdp, capture.path === "/" ? ".tourist-shell" : ".admin-shell");
    if (capture.click) {
      const clicked = await cdp.send("Runtime.evaluate", {
        expression: `(() => { const element = document.querySelector(${JSON.stringify(capture.click)}); if (!element) return false; element.click(); return true; })()`,
        returnByValue: true,
      });
      if (clicked.result?.value !== true) throw new Error(`Could not click ${capture.click}.`);
    }
    await waitForSelector(cdp, capture.ready);
    const screenshot = await cdp.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    });
    const output = join(outputDir, `${capture.name}.png`);
    writeFileSync(output, Buffer.from(screenshot.data, "base64"));
    console.log(JSON.stringify({ name: capture.name, output }));
  }
} finally {
  cdp?.close();
  if (browser.exitCode === null) {
    browser.kill();
    await Promise.race([new Promise((resolveExit) => browser.once("exit", resolveExit)), delay(3_000)]);
  }
  await delay(2_000);
  const safeTempRoot = `${resolve(tmpdir())}${sep}`.toLowerCase();
  const resolvedProfile = resolve(profile);
  if (!resolvedProfile.toLowerCase().startsWith(safeTempRoot)) {
    throw new Error(`Refusing to remove non-temp browser profile: ${resolvedProfile}`);
  }
  for (let attempt = 1; attempt <= 30; attempt += 1) {
    try {
      rmSync(resolvedProfile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (!["EBUSY", "EPERM"].includes(error?.code)) throw error;
      if (attempt === 30) {
        console.warn(JSON.stringify({ warning: "temporary Edge profile is still locked", profile: resolvedProfile }));
        break;
      }
      await delay(500);
    }
  }
}
