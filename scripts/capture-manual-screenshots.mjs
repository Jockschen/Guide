import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import net from "node:net";

const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const workspace = process.cwd();
const outputDir = join(workspace, "docs", "assets", "manual");
const baseUrl = process.env.MANUAL_SCREENSHOT_BASE_URL || "http://127.0.0.1:3000";
const profile = mkdtempSync(join(tmpdir(), "lingjing-manual-cdp-"));
const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

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
  const deadline = Date.now() + 20_000;
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
  const exceptions = [];
  let requestId = 0;

  await new Promise((resolveOpen, reject) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      exceptions.push(message.params?.exceptionDetails?.text || "Runtime exception");
    }
    if (!message.id || !pending.has(message.id)) return;
    const { resolveRequest, rejectRequest } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) rejectRequest(new Error(message.error.message));
    else resolveRequest(message.result || {});
  });

  return {
    exceptions,
    send(method, params = {}) {
      requestId += 1;
      const id = requestId;
      const response = new Promise((resolveRequest, rejectRequest) => {
        pending.set(id, { resolveRequest, rejectRequest });
      });
      socket.send(JSON.stringify({ id, method, params }));
      return response;
    },
    close() {
      socket.close();
    },
  };
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return result.result?.value;
}

async function waitFor(cdp, expression, label, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await evaluate(cdp, expression)) return;
    await delay(200);
  }
  throw new Error(`Timed out waiting for ${label}.`);
}

async function navigate(cdp, path, readySelector) {
  await cdp.send("Page.navigate", { url: `${baseUrl}${path}` });
  await waitFor(
    cdp,
    `document.readyState === "complete" && Boolean(document.querySelector(${JSON.stringify(readySelector)}))`,
    readySelector,
  );
  await delay(2_500);
}

async function clickButton(cdp, label) {
  const clicked = await evaluate(
    cdp,
    `(() => {
      const button = [...document.querySelectorAll("button")]
        .find((item) => item.textContent?.replace(/\\s+/g, " ").trim().includes(${JSON.stringify(label)}));
      if (!button) return false;
      button.click();
      return true;
    })()`,
  );
  if (!clicked) throw new Error(`Button not found: ${label}`);
}

async function capture(cdp, filename) {
  const hasOverlay = await evaluate(
    cdp,
    `Boolean(document.querySelector("[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay"))`,
  );
  const hasContent = await evaluate(cdp, `document.body.innerText.trim().length > 0`);
  if (hasOverlay || !hasContent) throw new Error(`Page validation failed before ${filename}.`);
  const screenshot = await cdp.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  const output = join(outputDir, filename);
  writeFileSync(output, Buffer.from(screenshot.data, "base64"));
  console.log(JSON.stringify({ output, hasContent, hasOverlay }));
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
  "--hide-scrollbars",
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

  await navigate(cdp, "/", ".tourist-shell");
  await capture(cdp, "01-tourist-home.png");

  await clickButton(cdp, "灵山大照壁在哪里");
  await waitFor(
    cdp,
    `(() => {
      const answers = [...document.querySelectorAll(".message.assistant .markdown-body")];
      const latest = answers.at(-1);
      return Boolean(latest && latest.textContent.trim().length > 20 && !document.querySelector(".loading-message"));
    })()`,
    "completed scenic-area answer",
    60_000,
  );
  await delay(2_000);
  await capture(cdp, "07-tourist-answer.png");

  await clickButton(cdp, "推荐游线");
  await waitFor(cdp, `Boolean(document.querySelector(".itinerary-panel"))`, "recommended itinerary", 30_000);
  await delay(1_500);
  await capture(cdp, "02-tourist-route.png");

  await navigate(cdp, "/admin", ".admin-shell");
  await capture(cdp, "03-admin-overview.png");

  await clickButton(cdp, "知识内容");
  await waitFor(cdp, `Boolean(document.querySelector(".knowledge-area"))`, "knowledge area");
  await delay(1_000);
  await capture(cdp, "04-admin-knowledge.png");

  await clickButton(cdp, "游客感受");
  await waitFor(cdp, `Boolean(document.querySelector(".feedback-area"))`, "feedback area");
  await delay(1_000);
  await capture(cdp, "05-admin-feedback.png");

  await clickButton(cdp, "质量报告");
  await waitFor(cdp, `Boolean(document.querySelector(".quality-area"))`, "quality area");
  await delay(1_000);
  await capture(cdp, "06-admin-quality.png");

  if (cdp.exceptions.length) {
    throw new Error(`Browser exceptions: ${cdp.exceptions.join(" | ")}`);
  }
} finally {
  cdp?.close();
  if (browser.exitCode === null) {
    browser.kill();
    await Promise.race([
      new Promise((resolveExit) => browser.once("exit", resolveExit)),
      delay(5_000),
    ]);
  }
  const safeTempRoot = `${resolve(tmpdir())}${sep}`.toLowerCase();
  const resolvedProfile = resolve(profile);
  if (!resolvedProfile.toLowerCase().startsWith(safeTempRoot)) {
    throw new Error(`Refusing to remove non-temp browser profile: ${resolvedProfile}`);
  }
  for (let attempt = 1; attempt <= 20; attempt += 1) {
    try {
      rmSync(resolvedProfile, { recursive: true, force: true });
      break;
    } catch (error) {
      if (!["EBUSY", "EPERM"].includes(error?.code)) throw error;
      if (attempt === 20) console.warn(`Temporary browser profile is still locked: ${resolvedProfile}`);
      else await delay(250);
    }
  }
}
