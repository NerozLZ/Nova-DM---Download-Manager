"use strict";
// Envia para o Nova DM (127.0.0.1) os downloads iniciados no Firefox.
// Só cancela o download do Firefox depois de o Nova DM o ter aceitado; se o Nova DM não estiver
// aberto, o Firefox descarrega normalmente.

const DEFAULTS = { enabled: true, port: 17650, token: "", ignoredHosts: "", autoLaunch: true };
const LAUNCH_WAIT_SECONDS = 25;
const LAUNCH_COOLDOWN_MS = 5 * 60 * 1000;
let launching = null;
let lastLaunchFailure = 0;

async function getSettings() {
  return Object.assign({}, DEFAULTS, await browser.storage.local.get(DEFAULTS));
}

function isIgnored(url, ignoredHosts) {
  let host;
  try { host = new URL(url).hostname; } catch (e) { return true; }
  return ignoredHosts.split(/[\s,]+/).filter(Boolean)
    .some((h) => host === h || host.endsWith("." + h));
}

async function cookieHeader(url) {
  try {
    const cookies = await browser.cookies.getAll({ url });
    return cookies.map((c) => c.name + "=" + c.value).join("; ");
  } catch (e) {
    return "";
  }
}

function baseName(path) {
  return (path || "").split(/[\\/]/).pop() || "";
}

async function sendToNovaDM(item, settings) {
  const body = {
    urls: [item.url],
    referer: item.referrer || "",
    user_agent: navigator.userAgent,
    cookies: await cookieHeader(item.url),
    filename: baseName(item.filename),
  };
  const response = await fetch("http://127.0.0.1:" + settings.port + "/v1/links", {
    method: "POST",
    headers: { "Authorization": "Bearer " + settings.token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return response.ok;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// "ok" = Nova DM aceita o token; "refused" = Nova DM aberto mas recusou; "down" = não está a escutar.
async function ping(settings) {
  try {
    const response = await fetch("http://127.0.0.1:" + settings.port + "/v1/ping", {
      headers: { "Authorization": "Bearer " + settings.token }, cache: "no-store",
    });
    return response.ok ? "ok" : "refused";
  } catch (e) {
    return "down";
  }
}

// Abre o Nova DM através do endereço novadm:// (registado pelo ficheiro .desktop).
async function launchNovaDM(settings) {
  const tab = await browser.tabs.create({ url: "novadm://start", active: false });
  setTimeout(() => browser.tabs.remove(tab.id).catch(() => {}), 3000);
  for (let i = 0; i < LAUNCH_WAIT_SECONDS; i++) {
    await sleep(1000);
    if ((await ping(settings)) !== "down") return true;
  }
  lastLaunchFailure = Date.now();
  return false;
}

// Devolve true se o Nova DM está pronto a receber (abrindo-o se estiver fechado e for permitido).
async function ensureRunning(settings) {
  const state = await ping(settings);
  if (state === "ok") return true;
  if (state === "refused" || !settings.autoLaunch) return false;
  if (Date.now() - lastLaunchFailure < LAUNCH_COOLDOWN_MS) return false;
  if (!launching) {
    launching = launchNovaDM(settings).finally(() => { launching = null; });
  }
  return launching;
}

browser.downloads.onCreated.addListener(async (item) => {
  try {
    const settings = await getSettings();
    if (!settings.enabled || !settings.token) return;
    if (!/^https?:\/\//i.test(item.url) || isIgnored(item.url, settings.ignoredHosts)) return;
    if (!(await ensureRunning(settings))) return;
    // Se o Firefox terminou o download enquanto o Nova DM abria, deixa-o ficar no Firefox.
    const [current] = await browser.downloads.search({ id: item.id });
    if (!current || current.state !== "in_progress") return;
    if (!(await sendToNovaDM(item, settings))) return;
    await browser.downloads.cancel(item.id);
    await browser.downloads.erase({ id: item.id });
  } catch (e) {
    // Nova DM fechado ou token errado: deixa o Firefox continuar o download.
  }
});

async function refreshButton() {
  const { enabled } = await getSettings();
  await browser.browserAction.setBadgeText({ text: enabled ? "" : "off" });
  await browser.browserAction.setTitle({ title: "Nova DM — " + (enabled ? "on" : "off") });
}

browser.browserAction.onClicked.addListener(async () => {
  const { enabled } = await getSettings();
  await browser.storage.local.set({ enabled: !enabled });
});
browser.storage.onChanged.addListener(refreshButton);
refreshButton();
