"use strict";
const DEFAULTS = { enabled: true, port: 17650, token: "", ignoredHosts: "", autoLaunch: true };
const $ = (id) => document.getElementById(id);

browser.storage.local.get(DEFAULTS).then((s) => {
  $("enabled").checked = s.enabled;
  $("autolaunch").checked = s.autoLaunch;
  $("port").value = s.port;
  $("token").value = s.token;
  $("ignored").value = s.ignoredHosts;
});

$("save").addEventListener("click", async () => {
  const s = {
    enabled: $("enabled").checked,
    autoLaunch: $("autolaunch").checked,
    port: Number($("port").value) || DEFAULTS.port,
    token: $("token").value.trim(),
    ignoredHosts: $("ignored").value,
  };
  await browser.storage.local.set(s);
  try {
    const r = await fetch("http://127.0.0.1:" + s.port + "/v1/ping", {
      headers: { "Authorization": "Bearer " + s.token }, cache: "no-store",
    });
    $("status").textContent = r.ok ? "Connected to Nova DM." : "Nova DM refused the token or port.";
  } catch (e) {
    $("status").textContent = "Cannot reach Nova DM. Is it open with browser integration enabled?";
  }
});

$("connect").addEventListener("click", async () => {
  const port = Number($("port").value) || DEFAULTS.port;
  $("status").textContent = "Confirm the request in the Nova DM window…";
  try {
    const r = await fetch("http://127.0.0.1:" + port + "/v1/pair", { method: "POST", cache: "no-store" });
    if (!r.ok) {
      $("status").textContent = r.status === 403 ? "Nova DM: connection refused." : "Nova DM is busy, try again.";
      return;
    }
    const { token } = await r.json();
    $("token").value = token;
    await browser.storage.local.set({ port, token, enabled: true });
    $("enabled").checked = true;
    $("status").textContent = "Connected to Nova DM.";
  } catch (e) {
    $("status").textContent = "Cannot reach Nova DM. Is it open with browser integration enabled?";
  }
});
