#!/usr/bin/env node
/**
 * Records chapter 4 of the OSLab introduction film: the web dashboard launching a real run.
 *
 * The script starts its own dashboard from this checkout, so the operator's dashboard keeps running:
 * the API on --api-port with a new SQLite database in a temporary folder, and the web app on
 * --web-port from a temporary copy of apps/web with its own .next build. It signs in with a random
 * password and records a headless Chromium session: the overview, the Run Launcher with the scenario,
 * the artifact and the options, the launch, the live console until the run finishes, and the run in
 * the Results Explorer with its evidence, timeline and HTML report. Then it stops both servers and
 * deletes the temporary files and the dashboard's job log.
 *
 * Files written to --out. The film editor reads dashboard.mkv, dashboard.json, actions.json,
 * chapters.json and boxes.json.
 * - dashboard.mkv and dashboard.json: the page at a constant 30 fps, assembled from timestamped
 *   Page.startScreencast PNG frames, and {t0, width, height, seconds, fps}.
 * - actions.json: every pointer move, click, typed text, scroll and wait, in viewport CSS pixels,
 *   which are video pixels because the page renders at a device scale factor of 1.
 * - chapters.json: epochs of the launch click, the first live log line, the finished run, the opened
 *   Results Explorer and the shown report.
 * - boxes.json: the boxes [x0, y0, x1, y1] of the live console, the result detail and the report
 *   preview in video pixels, each with the epoch it was measured on screen, for the editor's zoom.
 * - run.json and progress.jsonl: copies from runs/<run id>/.
 * - aliases.json: the find and replace pairs applied to the page.
 *
 * Lab names never reach the screen. A route rewrites the dashboard API responses, including the
 * sandboxed report frame, and an init script rewrites text, attributes and input values that arrive
 * another way, such as the live log stream. During the whole session the visible text is checked
 * against the private names and config/public-release-blocklist.local.txt.
 *
 * The web app sends live log streams to port 3001 of the page host. Chromium maps that port to
 * --api-port with --host-resolver-rules, so the operator's API on port 3001 never sees this session.
 *
 * The dashboard hides *.local.yaml scenarios and refuses paths that contain .local. or .private., so
 * --scenario must be another gitignored copy with the lab's template and VMID range, such as
 * scenarios/windows/qa-demo-agent-steps.example.yaml (ignored as qa-*.example.yaml) or a file under
 * scenarios/<os>/private/.
 *
 * Run it from the repository root as one command:
 *
 *   node validation/artifacts/intro-video/capture_dashboard.mjs
 *     --out <capture folder>/dashboard
 *     --scenario scenarios/windows/qa-demo-agent-steps.example.yaml
 *     --artifact validation/artifacts/demo-agent-cli
 *     --ffmpeg <ffmpeg.exe>
 *     [--chromium <chrome.exe>]   a browser binary when Playwright's own Chromium is not installed
 */

import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import { copyFile, cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import { createRequire } from "node:module";
import { connect } from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import { chromium } from "@playwright/test";

const REPO = path.resolve(fileURLToPath(new URL("../../../", import.meta.url)));
const API_DIR = path.join(REPO, "apps", "api");
const WEB_DIR = path.join(REPO, "apps", "web");
const PRISMA_CLI = path.join(API_DIR, "node_modules", "prisma", "build", "index.js");
const PRISMA_SCHEMA = path.join(API_DIR, "prisma", "schema.prisma");
const NEXT_CLI = path.join(WEB_DIR, "node_modules", "next", "dist", "bin", "next");
const YAML = createRequire(path.join(API_DIR, "package.json"))("yaml");

// 16:10 like the VM consoles in the film. At this width the Run Launcher is one column with the live
// console under the form, and the console is a scroll box that follows the newest line.
const WIDTH = 1280;
const HEIGHT = 800;
const FPS = 30;
const USERNAME = "operator";
const PAGE_HOST = "localhost";
// getApiBaseUrl() in apps/web sends live log streams and uploads to this port of the page host.
const DIRECT_API_PORT = 3001;
// Public stand-ins. The first four are the ones capture_cli.py uses, so every chapter shows the same names.
const API_HOST = "proxmox.example.local";
const NODE = "pve01";
const USER_FOLDER = "C:\\Users\\demo";
const COMPUTER = "OSLAB-WIN11";
const TEMPLATE = "win11-template";
const OTHER_VM = "lab-vm";
const HOST_COMPUTER = "capture-host";
const PRIVATE_WORD = "product";

const { values: options } = parseArgs({
  options: {
    out: { type: "string" },
    scenario: { type: "string" },
    artifact: { type: "string", default: "validation/artifacts/demo-agent-cli" },
    config: { type: "string", default: "config/oslab.local.yaml" },
    "env-file": { type: "string", default: "config/oslab.local.env" },
    blocklist: { type: "string", default: "config/public-release-blocklist.local.txt" },
    ffmpeg: { type: "string", default: "ffmpeg" },
    chromium: { type: "string" },
    "web-port": { type: "string", default: "3100" },
    "api-port": { type: "string", default: "3101" },
    "run-timeout-minutes": { type: "string", default: "20" },
  },
});
if (!options.out || !options.scenario) throw new Error("--out <folder> and --scenario <gitignored scenario copy> are required");
const outDir = path.resolve(options.out);
const webPort = Number(options["web-port"]);
const apiPort = Number(options["api-port"]);
const webUrl = "http://" + PAGE_HOST + ":" + webPort;
const runTimeout = Number(options["run-timeout-minutes"]) * 60;
// The job and the run that this session starts, for the waits and the cleanup.
const state = { jobId: null, runId: null, jobStatus: null };
// Dashboard processes, stopped at the end.
const servers = [];

const now = () => Date.now() / 1000;
const sleep = (seconds) => new Promise((resolve) => setTimeout(resolve, seconds * 1000));
const random = (low, high) => low + Math.random() * (high - low);
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const round = (value, digits) => Number(value.toFixed(digits));

function log(message) {
  console.log(new Date().toTimeString().slice(0, 8) + " " + message);
}

// Privacy ----------------------------------------------------------------------------------------

/** Replaces private names with public stand-ins. Self-contained, because the page runs it too. */
function aliasText(value, spec) {
  const keepCase = (match, replacement) => {
    if (match === match.toUpperCase()) return replacement.toUpperCase();
    if (match[0] === match[0].toUpperCase()) return replacement[0].toUpperCase() + replacement.slice(1);
    return replacement;
  };
  let text = value;
  for (const row of spec.literals) {
    if (!text.toLowerCase().includes(row.lower)) continue;
    text = text.replace(new RegExp(row.escaped, "gi"), (match) => (row.keepCase ? keepCase(match, row.replace) : row.replace));
  }
  for (const row of spec.patterns) text = text.replace(new RegExp(row.source, row.flags), row.replace);
  return text;
}

/** Labels of the private names that remain in a text. Self-contained, because the page runs it too. */
function findLeaks(text, spec) {
  const lower = text.toLowerCase();
  const labels = spec.markers.filter((marker) => lower.includes(marker.lower)).map((marker) => marker.label);
  for (const row of spec.markerPatterns) {
    if (new RegExp(row.source, row.flags).test(text)) labels.push(row.label);
  }
  return labels;
}

function aliasJson(value, spec) {
  if (typeof value === "string") return aliasText(value, spec);
  if (Array.isArray(value)) return value.map((item) => aliasJson(item, spec));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, aliasJson(item, spec)]));
  }
  return value;
}

function aliasBody(body, type, spec) {
  if (type.includes("application/json")) {
    try {
      return JSON.stringify(aliasJson(JSON.parse(body), spec));
    } catch {
      // A JSON content type with another body falls back to plain text.
    }
  }
  return aliasText(body, spec);
}

/**
 * Runs in every page before its own scripts. Rewrites text, attributes and input values before the
 * browser paints them, and reports any private name that is still left.
 */
function pageAliasLayer(spec, aliasText, findLeaks) {
  const attributes = ["title", "placeholder", "aria-label", "alt", "label", "value"];
  const report = (text, where) => {
    const labels = findLeaks(text, spec);
    if (labels.length && window.oslabPrivacyLeak) window.oslabPrivacyLeak(labels, where);
  };
  const scrubText = (node) => {
    if (node.parentNode && ["SCRIPT", "STYLE"].includes(node.parentNode.nodeName)) return;
    const value = aliasText(node.data, spec);
    if (value !== node.data) node.data = value;
    report(value, "text");
  };
  const scrubElement = (element) => {
    for (const name of attributes) {
      const current = element.getAttribute(name);
      if (current === null) continue;
      const value = aliasText(current, spec);
      if (value !== current) element.setAttribute(name, value);
      report(value, name + " attribute");
    }
  };
  const scrubTree = (root) => {
    if (root.nodeType === Node.TEXT_NODE) return scrubText(root);
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    scrubElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeType === Node.TEXT_NODE) scrubText(node);
      else scrubElement(node);
    }
  };
  // React sets input values through the property, which a MutationObserver does not see.
  for (const prototype of [HTMLInputElement.prototype, HTMLTextAreaElement.prototype]) {
    const property = Object.getOwnPropertyDescriptor(prototype, "value");
    Object.defineProperty(prototype, "value", {
      ...property,
      set(value) {
        property.set.call(this, typeof value === "string" ? aliasText(value, spec) : value);
      },
    });
  }
  // Mutation callbacks run as microtasks, so they finish before the next paint.
  new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "characterData") scrubText(record.target);
      else if (record.type === "attributes") scrubElement(record.target);
      else record.addedNodes.forEach(scrubTree);
    }
  }).observe(document, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: attributes });
}

function parseEnvFile(content) {
  const values = {};
  for (const raw of content.replace(/^\uFEFF/, "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const index = line.indexOf("=");
    values[line.slice(0, index).trim()] = line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "");
  }
  return values;
}

/** A read-only Proxmox API client with the dashboard's token and user agent. */
function proxmoxClient(proxmox, env) {
  const base = String(proxmox.apiUrl).replace(/\/+$/, "");
  const apiBase = base.endsWith("/api2/json") ? base : base + "/api2/json";
  const secret = (name) => process.env[name] || env[name] || "";
  const authorization = "PVEAPIToken=" + secret(proxmox.tokenEnv?.id) + "=" + secret(proxmox.tokenEnv?.secret);
  return {
    get(endpoint) {
      const url = new URL(apiBase + endpoint);
      const transport = url.protocol === "http:" ? http : https;
      return new Promise((resolve, reject) => {
        const request = transport.request(url, {
          headers: { Accept: "application/json", Authorization: authorization, "User-Agent": "oslab/0.1.0" },
          rejectUnauthorized: proxmox.verifyTls !== false,
          timeout: 30_000,
        }, (response) => {
          const chunks = [];
          response.on("data", (chunk) => chunks.push(chunk));
          response.on("end", () => {
            if (response.statusCode >= 400) return reject(new Error("Proxmox " + endpoint + " answered HTTP " + response.statusCode));
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")).data);
          });
        });
        request.on("timeout", () => request.destroy(new Error("Proxmox " + endpoint + " timed out")));
        request.on("error", reject);
        request.end();
      });
    },
  };
}

/** Private names, their stand-ins and the markers that must never be visible. */
async function loadPrivacy() {
  const config = YAML.parse(await readFile(path.join(REPO, options.config), "utf8")) ?? {};
  const proxmox = config.providerDefaults?.proxmox ?? {};
  const env = parseEnvFile(await readFile(path.join(REPO, options["env-file"]), "utf8"));
  const blocklist = (await readFile(path.join(REPO, options.blocklist), "utf8").catch(() => ""))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));
  const lab = proxmoxClient(proxmox, env);
  const machines = await lab.get("/cluster/resources?type=vm");
  const templates = machines.filter((vm) => vm.template && vm.name).map((vm) => vm.name);
  // Only names with a digit or a hyphen, so that a short common word never rewrites the interface.
  const otherVms = machines.filter((vm) => !vm.template && /^(?=.*[\d-]).{6,}$/.test(vm.name ?? "")).map((vm) => vm.name);
  const apiHost = new URL(proxmox.apiUrl).hostname;
  const profile = os.homedir();
  const username = os.userInfo().username;
  const keys = Object.keys(env);
  const publicKeys = keys.filter((key) => !blocklist.some((marker) => key.toLowerCase().includes(marker.toLowerCase())));
  const secrets = Object.values(env).filter((value) => value.length >= 6);
  const literals = [
    // The API host comes first by length too: its name contains the node and user names.
    { find: apiHost, replace: API_HOST },
    // oslab lists the variables it loaded from the env file. Keep only the public names, as capture_cli.py does.
    { find: keys.join(", "), replace: publicKeys.join(", ") || "<none>" },
    { find: profile, replace: USER_FOLDER },
    { find: profile.replaceAll("\\", "/"), replace: USER_FOLDER.replaceAll("\\", "/") },
    { find: profile.replaceAll("\\", "\\\\"), replace: USER_FOLDER.replaceAll("\\", "\\\\") },
    { find: String(proxmox.node ?? ""), replace: NODE },
    { find: username, replace: "demo" },
    { find: os.hostname(), replace: HOST_COMPUTER },
    ...templates.map((name) => ({ find: name, replace: TEMPLATE })),
    ...otherVms.map((name) => ({ find: name, replace: OTHER_VM })),
    ...blocklist.map((marker) => ({ find: marker, replace: PRIVATE_WORD, keepCase: true })),
    ...secrets.map((value) => ({ find: value, replace: "<redacted>", secret: true })),
  ].filter((row) => row.find.length >= 3 && row.find !== row.replace);
  // A stand-in that contains a private name would grow every time the page rewrites the same text.
  for (const row of literals) {
    if (literals.some((other) => row.replace.toLowerCase().includes(other.find.toLowerCase()))) {
      throw new Error("A public stand-in contains a private name; change the stand-ins at the top of this script");
    }
  }
  const markers = [
    { label: "Proxmox API host", value: apiHost },
    { label: "Proxmox node", value: String(proxmox.node ?? "") },
    { label: "user name", value: username },
    { label: "computer name", value: os.hostname() },
    ...templates.map((value) => ({ label: "template name", value })),
    ...otherVms.map((value) => ({ label: "name of a VM that this run did not create", value })),
    ...blocklist.map((value, index) => ({ label: "blocklist marker " + (index + 1), value })),
    ...secrets.map((value, index) => ({ label: "env file value " + (index + 1), value, secret: true })),
  ].filter((marker) => marker.value.length >= 3);
  const spec = {
    literals: literals
      .sort((a, b) => b.find.length - a.find.length)
      .map((row) => ({ ...row, lower: row.find.toLowerCase(), escaped: row.find.replace(/[.*+?^$()|[\]{}\\]/g, "\\$&") })),
    patterns: [
      { source: String.raw`([A-Za-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/))[^\\/"'\s<>:|*?]+`, flags: "gi", replace: "$1demo" },
      { source: String.raw`\b(?:DESKTOP|LAPTOP|WIN)-[A-Z0-9]{7,11}\b`, flags: "g", replace: COMPUTER },
    ],
    markers: markers.map((marker) => ({ ...marker, lower: marker.value.toLowerCase() })),
    markerPatterns: [
      { label: "Windows user folder", source: String.raw`[A-Za-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)(?!demo(?![\w.-]))[^\\/"'\s<>:|*?]+`, flags: "i" },
      { label: "guest computer name", source: String.raw`\b(?:DESKTOP|LAPTOP|WIN)-[A-Z0-9]{7,11}\b`, flags: "" },
    ],
  };
  return { spec, lab };
}

/** The pairs for aliases.json, in the order they are applied. Env file values stay out of it. */
function aliasRows(spec) {
  return [
    ...spec.literals.filter((row) => !row.secret).map((row) => ({ find: row.find, replace: row.replace, ignoreCase: true, ...(row.keepCase ? { keepCase: true } : {}) })),
    ...spec.patterns.map((row) => ({ pattern: row.source, flags: row.flags, replace: row.replace })),
  ];
}

async function installPrivacy(context, spec, leaks) {
  // Env file values stay out of the page: the dashboard already redacts them in job logs.
  const pageSpec = {
    literals: spec.literals.filter((row) => !row.secret),
    patterns: spec.patterns,
    markers: spec.markers.filter((marker) => !marker.secret),
    markerPatterns: spec.markerPatterns,
  };
  await context.exposeBinding("oslabPrivacyLeak", (source, labels, where) => leaks.push({ t: now(), labels, where }));
  await context.addInitScript({ content: "(" + pageAliasLayer + ")(" + JSON.stringify(pageSpec) + ", " + aliasText + ", " + findLeaks + ");" });
  const origin = PAGE_HOST + ":" + webPort;
  const routed = (url) => url.host === origin && url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/auth/");
  await context.route(routed, async (route) => {
    const response = await route.fetch();
    const type = response.headers()["content-type"] || "";
    if (!/json|text|html|xml/.test(type)) return route.fulfill({ response });
    const body = aliasBody(await response.text(), type, spec);
    const labels = findLeaks(body, spec);
    if (labels.length) leaks.push({ t: now(), labels, where: "response of " + new URL(route.request().url()).pathname });
    return route.fulfill({ response, body });
  });
}

/** Checks the visible text of every frame, including input values, until active() turns false. */
async function checkVisibleText(page, spec, privacy, active) {
  while (active()) {
    for (const frame of page.frames()) {
      const text = await frame.evaluate(() => {
        const parts = [document.body ? document.body.innerText : ""];
        for (const field of document.querySelectorAll("input, textarea")) parts.push(field.value);
        return parts.join("\n");
      }).catch(() => "");
      const labels = findLeaks(text, spec);
      if (labels.length) privacy.leaks.push({ t: now(), labels, where: "visible text" });
    }
    privacy.scans += 1;
    await sleep(0.4);
  }
}

// Dashboard servers ------------------------------------------------------------------------------

function isListening(port) {
  return new Promise((resolve) => {
    const socket = connect({ host: "127.0.0.1", port });
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
  });
}

function runToEnd(name, command, args, cwd, env, spec) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, windowsHide: true });
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += chunk;
    });
    child.stderr.on("data", (chunk) => {
      output += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(name + " exited with code " + code + ":\n" + aliasText(output.slice(-3000), spec)));
    });
  });
}

function startServer(name, args, cwd, env, scratch) {
  const child = spawn(process.execPath, args, { cwd, env: { ...process.env, ...env }, windowsHide: true });
  const output = createWriteStream(path.join(scratch, name + ".log"));
  child.stdout.pipe(output);
  child.stderr.pipe(output);
  servers.push({ name, child, logPath: path.join(scratch, name + ".log") });
}

async function waitForHttp(url, spec) {
  const deadline = now() + 120;
  while (now() < deadline) {
    const exited = servers.find((server) => server.child.exitCode !== null);
    if (exited) {
      const tail = (await readFile(exited.logPath, "utf8").catch(() => "")).slice(-3000);
      throw new Error("The " + exited.name + " server stopped:\n" + aliasText(tail, spec));
    }
    const ok = await fetch(url).then((response) => response.status < 500).catch(() => false);
    if (ok) return;
    await sleep(0.5);
  }
  throw new Error("Timed out waiting for " + url);
}

/** A copy of apps/web, so the capture build gets its own .next folder. */
async function copyWebApp(scratch) {
  const copy = path.join(scratch, "web");
  await mkdir(copy);
  for (const name of ["package.json", "tsconfig.json", "next-env.d.ts", "next.config.mjs"]) {
    await copyFile(path.join(WEB_DIR, name), path.join(copy, name));
  }
  for (const name of ["src", "public"]) await cp(path.join(WEB_DIR, name), path.join(copy, name), { recursive: true });
  await symlink(path.join(WEB_DIR, "node_modules"), path.join(copy, "node_modules"), "junction");
  return copy;
}

async function startDashboard(scratch, password, spec) {
  for (const port of [webPort, apiPort]) {
    if (await isListening(port)) throw new Error("Port " + port + " is already in use. Stop that server or pick another port.");
  }
  const databaseUrl = "file:" + path.join(scratch, "dashboard.db").replaceAll("\\", "/");
  log("Creating the dashboard database");
  // Prisma 6.19 on Windows fails to create a new SQLite file with an empty "Schema engine error" unless RUST_LOG is set.
  await runToEnd("prisma db push", process.execPath, [PRISMA_CLI, "db", "push", "--schema", PRISMA_SCHEMA, "--skip-generate"], scratch,
    { DATABASE_URL: databaseUrl, RUST_LOG: "info" }, spec);
  log("Starting the API on port " + apiPort);
  startServer("api", ["--import", "tsx", "src/main.ts"], API_DIR, {
    DATABASE_URL: databaseUrl,
    OSLAB_REPO_ROOT: REPO,
    OSLAB_API_PORT: String(apiPort),
    OSLAB_WEB_HOST: "127.0.0.1",
    OSLAB_WEB_ORIGIN: webUrl,
    OSLAB_WEB_ADMIN_USERNAME: USERNAME,
    OSLAB_WEB_ADMIN_PASSWORD: password,
  }, scratch);
  log("Building the web app in a temporary copy of apps/web");
  const webCopy = await copyWebApp(scratch);
  const webEnv = { OSLAB_API_PROXY: "http://127.0.0.1:" + apiPort, NEXT_TELEMETRY_DISABLED: "1" };
  await runToEnd("next build", process.execPath, [NEXT_CLI, "build"], webCopy, webEnv, spec);
  log("Starting the web app on port " + webPort);
  startServer("web", [NEXT_CLI, "start", "-H", "127.0.0.1", "-p", String(webPort)], webCopy, webEnv, scratch);
  await waitForHttp("http://127.0.0.1:" + apiPort + "/api/me", spec);
  await waitForHttp("http://127.0.0.1:" + webPort + "/", spec);
}

async function stopDashboard() {
  for (const server of servers) {
    if (server.child.exitCode !== null) continue;
    const exited = once(server.child, "exit");
    if (process.platform === "win32") {
      await runToEnd("taskkill", "taskkill", ["/PID", String(server.child.pid), "/T", "/F"], REPO, {}, { literals: [], patterns: [] }).catch(() => {});
    } else {
      server.child.kill("SIGTERM");
    }
    await Promise.race([exited, sleep(15)]);
  }
  for (const port of [webPort, apiPort]) {
    log("Port " + port + (await isListening(port) ? " still answers" : " is free"));
  }
}

// Recording --------------------------------------------------------------------------------------

/** A person at the mouse and keyboard. Every action goes to actions.json with the pointer position. */
class Operator {
  constructor(page, start) {
    this.page = page;
    this.x = start.x;
    this.y = start.y;
    this.actions = [];
  }

  record(type, label, extra = {}) {
    const t = now();
    this.actions.push({ t: round(t, 3), type, x: round(this.x, 1), y: round(this.y, 1), ...extra, label });
    return t;
  }

  /** A point near the middle of the visible part of an element or a box, or the point itself. */
  async pointIn(target) {
    const box = typeof target.boundingBox === "function" ? await target.boundingBox() : target;
    if (!box) throw new Error("Cannot point at a hidden element: " + target);
    if (box.width === undefined) return box;
    const left = Math.max(box.x, 0);
    const right = Math.min(box.x + box.width, WIDTH);
    const top = Math.max(box.y, 0);
    const bottom = Math.min(box.y + box.height, HEIGHT);
    if (right - left < 2 || bottom - top < 2) throw new Error("Element is off screen: " + target);
    return { x: left + (right - left) * random(0.38, 0.62), y: top + (bottom - top) * random(0.4, 0.6) };
  }

  /** An eased path with a slight arc, sampled at 60 Hz. */
  async moveTo(target, label) {
    const end = await this.pointIn(target);
    const start = { x: this.x, y: this.y };
    const distance = Math.hypot(end.x - start.x, end.y - start.y);
    if (distance < 1) return;
    const seconds = clamp(0.22 + distance / 1600, 0.28, 1.0);
    const steps = Math.max(8, Math.round(seconds * 60));
    const bend = random(-0.15, 0.15) * distance;
    const control = {
      x: (start.x + end.x) / 2 - ((end.y - start.y) / distance) * bend,
      y: (start.y + end.y) / 2 + ((end.x - start.x) / distance) * bend,
    };
    for (let step = 1; step <= steps; step += 1) {
      const s = step / steps;
      const eased = s * s * s * (10 - 15 * s + 6 * s * s);
      this.x = (1 - eased) ** 2 * start.x + 2 * (1 - eased) * eased * control.x + eased ** 2 * end.x;
      this.y = (1 - eased) ** 2 * start.y + 2 * (1 - eased) * eased * control.y + eased ** 2 * end.y;
      await this.page.mouse.move(this.x, this.y);
      this.record("move", label);
      await sleep(seconds / steps);
    }
  }

  async moveInto(area, label) {
    const box = typeof area.boundingBox === "function" ? await area.boundingBox() : area;
    const inside = this.x >= box.x && this.x <= box.x + box.width && this.y >= box.y && this.y <= box.y + box.height;
    if (!inside) await this.moveTo(area, label);
  }

  async click(target, label) {
    const box = await target.boundingBox();
    if (!box || box.y < 0 || box.y + box.height > HEIGHT) throw new Error("Cannot click outside the viewport: " + label);
    await this.moveTo(target, label);
    await sleep(random(0.12, 0.25));
    await this.page.mouse.down();
    const t = this.record("click", label);
    await sleep(random(0.05, 0.1));
    await this.page.mouse.up();
    return t;
  }

  /** Screencast frames never show the native dropdown list, so the option is picked directly. */
  async choose(select, value, label) {
    await this.moveTo(select, label);
    await sleep(random(0.15, 0.3));
    const t = this.record("click", label, { value });
    await select.selectOption(value);
    return t;
  }

  async type(text, label) {
    const t = this.record("type", label, { text });
    for (const character of text) {
      await this.page.keyboard.type(character);
      await sleep(random(0.04, 0.1) + (character === "/" ? random(0.1, 0.2) : 0));
    }
    return t;
  }

  /**
   * Smooth strokes of the element's scroll container until the element sits between top and bottom.
   * The Run Launcher document is taller than its content, so wheel scrolling past the end of the
   * workspace would move the whole page and leave an empty band at the bottom of the screen.
   */
  async scrollTo(target, label, { area, top = 150, bottom = HEIGHT - 120 } = {}) {
    if (area) await this.moveInto(area, label);
    for (let stroke = 0; stroke < 8; stroke += 1) {
      const box = await target.boundingBox();
      if (!box) throw new Error("Cannot find " + label);
      const height = Math.min(box.height, bottom - top);
      if (box.y >= top && box.y + height <= bottom) return;
      const wanted = box.y + height / 2 - (top + bottom) / 2;
      const scrolled = await target.evaluate(scrollContainerBy, Math.sign(wanted) * Math.min(Math.abs(wanted), random(320, 480)));
      if (Math.abs(scrolled) < 1) return;
      this.record("scroll", label, { deltaY: Math.round(scrolled) });
      await sleep(random(0.55, 0.75));
    }
  }

  async wait(seconds, label) {
    this.record("wait", label, { seconds });
    await sleep(seconds);
  }
}

async function waitFor(page, predicate, timeoutSeconds, argument) {
  await page.waitForFunction(predicate, argument, { timeout: timeoutSeconds * 1000, polling: 100 });
  return now();
}

/** Smoothly scrolls the nearest scrollable ancestor of an element, never past its ends. Runs in the page. */
function scrollContainerBy(element, delta) {
  let container = element.parentElement;
  while (container && !(container.scrollHeight > container.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(container).overflowY))) {
    container = container.parentElement;
  }
  const scroller = container ?? document.scrollingElement;
  const room = delta > 0 ? scroller.scrollHeight - scroller.clientHeight - scroller.scrollTop : -scroller.scrollTop;
  const step = delta > 0 ? Math.min(delta, room) : Math.max(delta, room);
  scroller.scrollBy({ top: step, behavior: "smooth" });
  return step;
}

/** The job as the dashboard reports it, polled until it leaves the queued and running states. */
async function waitForJob(page) {
  const deadline = now() + runTimeout;
  while (now() < deadline) {
    const job = await page.evaluate(async (id) => (await fetch("/api/jobs/" + id, { credentials: "include" })).json(), state.jobId).catch(() => null);
    if (job && !["queued", "running"].includes(job.status)) {
      state.jobStatus = job.status;
      state.runId = job.runId;
      return job;
    }
    await sleep(3);
  }
  throw new Error("Job " + state.jobId + " did not finish within " + options["run-timeout-minutes"] + " minutes");
}

async function startScreencast(page, frameDirectory) {
  const session = await page.context().newCDPSession(page);
  const frames = [];
  const writes = [];
  session.on("Page.screencastFrame", (event) => {
    session.send("Page.screencastFrameAck", { sessionId: event.sessionId }).catch(() => {});
    const file = path.join(frameDirectory, String(frames.length).padStart(6, "0") + ".png");
    frames.push({ t: event.metadata.timestamp ?? now(), file });
    writes.push(writeFile(file, Buffer.from(event.data, "base64")));
  });
  await session.send("Page.startScreencast", { format: "png", maxWidth: WIDTH, maxHeight: HEIGHT, everyNthFrame: 1 });
  for (let attempt = 0; !frames.length && attempt < 50; attempt += 1) await sleep(0.1);
  if (!frames.length) throw new Error("The screencast sent no frame");
  return {
    frames,
    async stop() {
      const end = now();
      await session.send("Page.stopScreencast");
      await Promise.all(writes);
      return end;
    },
  };
}

async function signIn(page, password) {
  await page.goto(webUrl + "/");
  const fields = page.locator("form.loginPanel input");
  await fields.nth(0).fill(USERNAME);
  await fields.nth(1).fill(password);
  await page.locator("form.loginPanel button[type=submit]").click();
  await page.locator("aside.nav").waitFor({ timeout: 30_000 });
}

/** The live log stream must reach this script's API, not the dashboard that normally owns port 3001. */
async function checkDirectApi(page) {
  const url = "http://" + PAGE_HOST + ":" + DIRECT_API_PORT + "/api/me";
  const user = await page.evaluate(async (target) => (await (await fetch(target, { credentials: "include" })).json()).user?.username, url);
  if (user !== USERNAME) throw new Error("Port " + DIRECT_API_PORT + " of " + PAGE_HOST + " did not reach the capture API");
}

/** The element's box in video pixels at this moment, for the editor's zoom. */
async function measure(locator) {
  const box = await locator.boundingBox();
  return { t: round(now(), 3), box: [round(box.x, 1), round(box.y, 1), round(box.x + box.width, 1), round(box.y + box.height, 1)] };
}

/** The recorded session, from the overview to the HTML report of the new run. */
async function performSession(page, operator, moments, boxes) {
  const nav = (name) => page.locator("aside.nav button[title=\"" + name + "\"]");
  // Where the pointer rests while the Run Launcher scrolls.
  const launchArea = { x: 320, y: 260, width: 860, height: 420 };
  const consoleArea = { x: 700, y: 330, width: 460, height: 300 };
  const consolePanel = page.locator(".panel.console");

  await operator.wait(1.8, "Dashboard overview");
  await operator.moveTo(page.locator(".labStatus .statusCell").nth(2), "Lab status: template");
  await operator.wait(1.0, "Read the lab status");
  await operator.moveTo(page.locator(".metric").nth(4), "Run results");
  await operator.wait(0.8, "Read the counters");

  await operator.click(nav("Run Launcher"), "Open the Run Launcher");
  const scenarioSelect = page.locator("select").filter({ has: page.locator("option[value=\"" + options.scenario + "\"]") });
  await scenarioSelect.waitFor();
  await operator.wait(1.0, "Run Launcher");
  await operator.scrollTo(scenarioSelect, "Scroll to the scenario", { area: launchArea, top: 300, bottom: 680 });
  await operator.choose(scenarioSelect, options.scenario, "Choose the scenario");
  await waitFor(page, (scenario) => document.querySelector(".labStatus .muted")?.textContent === scenario
    && !document.querySelector(".labStatus .labActions button[disabled]"), 60, options.scenario);
  await operator.scrollTo(page.locator(".labStatus"), "Scroll up to the lab status", { area: launchArea, top: 100 });
  await operator.moveTo(page.locator(".labStatus .statusCell").nth(3), "Lab status: VMID pool");
  await operator.wait(1.4, "Lab status for the scenario");

  const artifactInput = page.locator("label", { hasText: "Test file/folder path" }).locator("input");
  await operator.scrollTo(artifactInput, "Scroll to the test file", { area: launchArea });
  await operator.click(artifactInput, "Click the test file path");
  await operator.type(options.artifact, "Type the artifact folder");
  await page.locator(".artifactStatus.ok").waitFor({ timeout: 20_000 });
  await operator.wait(1.0, "The artifact folder exists");

  const advanced = page.getByRole("button", { name: "Advanced options", exact: true });
  await operator.scrollTo(advanced, "Scroll to the options", { area: launchArea });
  await operator.click(advanced, "Open the advanced options");
  await page.locator(".advancedBox").waitFor();
  await operator.moveTo(page.locator(".advancedBox .checkLine").first(), "Keep VM after run stays off");
  await operator.wait(1.2, "Read the options");

  const runButton = page.getByRole("button", { name: "Run selected scenario", exact: true });
  await operator.scrollTo(runButton, "Scroll to review and run", { area: launchArea });
  await operator.moveTo(page.locator(".commandPreview").nth(1), "Scenario command");
  await operator.wait(1.5, "Read the scenario command");
  const launched = page.waitForResponse((response) => response.url().endsWith("/api/jobs/run-scenario") && response.request().method() === "POST");
  moments.launch = await operator.click(runButton, "Run selected scenario");
  const job = await (await launched).json();
  if (!job.id) throw new Error("The dashboard did not start a job: " + JSON.stringify(job).slice(0, 300));
  state.jobId = job.id;
  log("Job " + job.id + " started");

  // The run banner and the first log lines push the console down, so it is brought into view twice.
  await operator.scrollTo(consolePanel, "Scroll down to the live console", { area: consoleArea, top: 110, bottom: HEIGHT - 6 });
  moments.first_log = await waitFor(page, () => /\[(OK|\.\.)\]|==/.test(document.querySelector(".console pre")?.textContent ?? ""), 180);
  await sleep(1.5);
  await operator.scrollTo(consolePanel, "Keep the whole console in view", { area: consoleArea, top: 110, bottom: HEIGHT - 6 });
  boxes.live_console = await measure(consolePanel);
  await operator.moveTo(page.locator(".console pre"), "Watch the live log");
  await operator.wait(0.5, "Follow the run until it finishes");
  moments.finished = await waitFor(page, () => /Job status: (passed|failed|cancelled)/.test(document.querySelector(".console .consoleHeader .muted")?.textContent ?? ""), runTimeout);
  await waitForJob(page);
  log("Job " + state.jobId + " finished as " + state.jobStatus + " with run " + state.runId);
  await operator.moveTo(page.locator(".console .consoleHeader .muted"), "Job status");
  await operator.wait(1.8, "Read the job status and the end of the log");

  await operator.click(nav("Results Explorer"), "Open the Results Explorer");
  moments.results = await waitFor(page, (runId) => (document.querySelector(".resultDetail")?.textContent ?? "").includes(runId), 30, state.runId);
  await operator.wait(0.8, "Results Explorer");
  await operator.click(page.locator(".resultRow", { hasText: state.runId }), "Open the run");
  const detail = page.locator(".resultDetail");
  boxes.results = await measure(detail);
  await operator.moveTo(page.locator(".resultDetail h4", { hasText: "Evidence checklist" }).locator("span").first(), "Evidence checklist");
  await operator.wait(1.2, "Read the evidence checklist");
  await operator.scrollTo(page.locator(".resultDetail h4", { hasText: "Timeline" }), "Scroll to the checks and the timeline", { area: detail, top: 520 });
  await operator.wait(1.8, "Read the assertions and the timeline");
  const reportRow = page.locator(".resultDetail .evidenceRow", { hasText: "reports/result.html" });
  await operator.scrollTo(reportRow, "Scroll back to the reports", { area: detail });
  await operator.click(reportRow, "Open the HTML report");
  const report = page.frameLocator(".previewFrame");
  await report.locator("h1").waitFor({ timeout: 20_000 });
  moments.report = now();
  boxes.report = await measure(page.locator(".previewFrame"));
  await operator.wait(1.4, "Read the report");
  await operator.scrollTo(report.locator("h2", { hasText: "Assertions" }), "Scroll to the assertions", { area: page.locator(".previewFrame"), top: 220, bottom: 640 });
  await operator.wait(2.8, "Read the assertions");
}

async function recordSession(password, spec, frameDirectory) {
  await mkdir(frameDirectory);
  const browser = await chromium.launch({
    headless: true,
    executablePath: options.chromium,
    args: [
      // Direct calls of the web app to port 3001 of the page host go to this script's API.
      "--host-resolver-rules=MAP " + PAGE_HOST + ":" + DIRECT_API_PORT + " 127.0.0.1:" + apiPort,
      // Headless Chromium jumps instead of animating smooth scrolls unless this is set.
      "--enable-smooth-scrolling",
    ],
  });
  const privacy = { scans: 0, leaks: [] };
  let checking = true;
  let checker = Promise.resolve();
  try {
    const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1, locale: "en-US" });
    await installPrivacy(context, spec, privacy.leaks);
    await context.addInitScript(() => {
      try {
        window.localStorage.setItem("oslab.lang", "en");
      } catch {
        // Frames without storage keep their language.
      }
    });
    const page = await context.newPage();
    checker = checkVisibleText(page, spec, privacy, () => checking);
    try {
      await signIn(page, password);
      await checkDirectApi(page);
      const operator = new Operator(page, { x: 900, y: 470 });
      await page.mouse.move(operator.x, operator.y);
      await waitFor(page, () => {
        const badge = document.querySelector(".labStatus .statusBadge");
        return badge && !/checking|unknown/i.test(badge.textContent) && !document.querySelector(".labStatus .labActions button[disabled]");
      }, 60);
      await sleep(1);
      const screencast = await startScreencast(page, frameDirectory);
      const moments = {};
      const boxes = {};
      await performSession(page, operator, moments, boxes);
      const end = await screencast.stop();
      return { frames: screencast.frames, end, actions: operator.actions, moments, boxes, privacy };
    } catch (error) {
      // A started run destroys its VM only if its process keeps running, so let it finish before the API stops.
      if (state.jobId && !state.jobStatus) await waitForJob(page).catch(() => {});
      throw error;
    }
  } finally {
    checking = false;
    await checker;
    await browser.close();
  }
}

/** Writes one output frame per 1/30 s: the newest screencast frame at that moment. */
async function encodeVideo(frames, end, target) {
  const t0 = frames[0].t;
  const count = Math.floor((end - t0) * FPS) + 1;
  const first = await readFile(frames[0].file);
  const size = { width: first.readUInt32BE(16), height: first.readUInt32BE(20) };
  const scale = size.width === WIDTH && size.height === HEIGHT ? [] : ["-vf", "scale=" + WIDTH + ":" + HEIGHT + ":flags=lanczos"];
  const ffmpeg = spawn(options.ffmpeg, [
    "-v", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-", ...scale,
    "-c:v", "libx264", "-preset", "medium", "-crf", "8", "-pix_fmt", "yuv444p", "-g", String(FPS * 2), target,
  ], { stdio: ["pipe", "inherit", "inherit"], windowsHide: true });
  const closed = once(ffmpeg, "close");
  ffmpeg.stdin.on("error", () => {});
  let index = 0;
  let file = null;
  let image = null;
  for (let frame = 0; frame < count && ffmpeg.exitCode === null; frame += 1) {
    const moment = t0 + frame / FPS;
    while (index + 1 < frames.length && frames[index + 1].t <= moment) index += 1;
    if (frames[index].file !== file) {
      file = frames[index].file;
      image = await readFile(file);
    }
    if (!ffmpeg.stdin.write(image)) await once(ffmpeg.stdin, "drain");
  }
  ffmpeg.stdin.end();
  const [code] = await closed;
  if (code !== 0) throw new Error("ffmpeg exited with code " + code);
  return { t0, seconds: count / FPS, size };
}

async function vmIsGone(lab, vmId) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const machines = await lab.get("/cluster/resources?type=vm");
    if (!machines.some((vm) => Number(vm.vmid) === vmId)) return true;
    await sleep(3);
  }
  return false;
}

async function writeJson(name, value) {
  await writeFile(path.join(outDir, name), JSON.stringify(value, null, 2) + "\n", "utf8");
}

function summarize(session, video, run, vmId, vmGone) {
  log("Run " + run.runId + " finished as " + run.status);
  for (const [name, moment] of Object.entries(session.moments)) log("  " + name + " at +" + (moment - video.t0).toFixed(1) + " s");
  log("Video: " + video.seconds.toFixed(1) + " s at " + FPS + " fps from " + session.frames.length + " screencast frames of "
    + video.size.width + "x" + video.size.height);
  const counts = {};
  for (const action of session.actions) counts[action.type] = (counts[action.type] ?? 0) + 1;
  log("Actions: " + JSON.stringify(counts));
  const leaks = session.privacy.leaks;
  log("Privacy: " + session.privacy.scans + " checks of the visible text, " + leaks.length + " leaks"
    + (leaks.length ? ": " + JSON.stringify(leaks.slice(0, 5)) : ""));
  log("VM " + vmId + (vmGone ? " no longer exists on the cluster" : " STILL EXISTS on the cluster"));
}

async function main() {
  await mkdir(outDir, { recursive: true });
  const { spec, lab } = await loadPrivacy();
  log("Privacy: " + spec.literals.length + " replacements and " + spec.markers.length + " markers");
  const scratch = await mkdtemp(path.join(os.tmpdir(), "oslab-dashboard-capture-"));
  const password = randomBytes(18).toString("base64url");
  try {
    await startDashboard(scratch, password, spec);
    const session = await recordSession(password, spec, path.join(scratch, "frames"));
    log("Assembling " + session.frames.length + " screencast frames at " + FPS + " fps");
    const video = await encodeVideo(session.frames, session.end, path.join(outDir, "dashboard.mkv"));
    await writeJson("dashboard.json", { t0: video.t0, width: WIDTH, height: HEIGHT, seconds: video.seconds, fps: FPS });
    await writeJson("actions.json", session.actions);
    await writeJson("chapters.json", session.moments);
    await writeJson("boxes.json", session.boxes);
    await writeJson("aliases.json", aliasRows(spec));
    const runDir = path.join(REPO, "runs", state.runId);
    await copyFile(path.join(runDir, "run.json"), path.join(outDir, "run.json"));
    await copyFile(path.join(runDir, "logs", "progress.jsonl"), path.join(outDir, "progress.jsonl"));
    const run = JSON.parse(await readFile(path.join(runDir, "run.json"), "utf8"));
    const vmId = Number(run.details?.vm?.id);
    const vmGone = await vmIsGone(lab, vmId);
    summarize(session, video, run, vmId, vmGone);
    if (session.privacy.leaks.length || run.status !== "passed" || !vmGone) process.exitCode = 1;
  } finally {
    await stopDashboard();
    if (state.jobId) await rm(path.join(REPO, ".web-data", "jobs", state.jobId + ".log"), { force: true });
    await rm(scratch, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 });
  }
}

await main();

