// NA Developers Lead Capture - popup logic
const APP = "http://127.0.0.1:8765";
const $ = (id) => document.getElementById(id);

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function runInPage(tab, fnName) {
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["extract.js"] });
  const [res] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (name) => window[name] ? window[name]() : null,
    args: [fnName]
  });
  return res ? res.result : null;
}

async function getList() {
  const { leads = [] } = await chrome.storage.local.get("leads");
  return leads;
}
async function setList(leads) {
  await chrome.storage.local.set({ leads });
  $("count").textContent = leads.length;
}
function msg(text, ok = true) {
  $("msg").textContent = text;
  $("msg").style.color = ok ? "#0b7a3e" : "#c62828";
}

async function appOnline() {
  try {
    const r = await fetch(APP + "/ping", { cache: "no-store" });
    return r.ok;
  } catch (e) {
    return false;
  }
}

async function refreshApp() {
  const on = await appOnline();
  $("app").textContent = on ? "Wix Lead Bot app is open - ready to receive."
                            : "App not open. Open WixLeadBot.exe, or use Download .txt.";
  $("app").className = on ? "yes" : "wait";
  return on;
}

async function sendToApp(items) {
  const r = await fetch(APP + "/capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items })
  });
  if (!r.ok) throw new Error("App replied " + r.status);
  return r.json();
}

// ---------- This website: Wix or not ----------
async function checkWix(tab) {
  if (!tab || !/^https?:/.test(tab.url || "")) {
    $("wix").textContent = "Open a website to check it.";
    return;
  }
  try {
    const isWix = await runInPage(tab, "naIsWix");
    const host = new URL(tab.url).hostname.replace(/^www\./, "");
    $("wix").textContent = isWix ? `✔ ${host} is built on Wix` : `✖ ${host} is not a Wix site`;
    $("wix").className = "wix " + (isWix ? "yes" : "no");
  } catch (e) {
    $("wix").textContent = "Can't read this page (Chrome blocks some pages).";
  }
}

// ---------- Capture ----------
$("capture").addEventListener("click", async () => {
  const tab = await activeTab();
  $("capture").disabled = true;
  try {
    const data = await runInPage(tab, "naExtract");
    const found = (data && data.items) || [];
    const list = await getList();
    const known = new Set(list.map((x) => x.website.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0].toLowerCase()));
    const fresh = found.filter((x) => !known.has(x.website.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0].toLowerCase()));
    const where = [data && data.category, data && data.region].filter(Boolean).join(", ");
    $("pageinfo").textContent = `${found.length} websites on this page${where ? " (" + where + ")" : ""}, ${fresh.length} new.`;
    $("pageinfo").className = found.length ? "yes" : "no";
    if (!found.length) {
      msg("No business websites found on this page.", false);
    } else if (!fresh.length) {
      msg("Nothing new on this page.");
    } else {
      let sent = false;
      if (await refreshApp()) {
        try {
          const res = await sendToApp(fresh);
          sent = true;
          msg(`Sent ${res.received} to the app (${res.new} new). Go to the next page and capture again.`);
        } catch (e) { /* keep them in the saved list */ }
      }
      if (!sent) {
        await setList(list.concat(fresh));
        msg(`Saved ${fresh.length} to the list. Send them when the app is open.`);
      }
    }
  } catch (e) {
    msg("Couldn't read this page: " + e.message, false);
  } finally {
    $("capture").disabled = false;
  }
});

// ---------- Google Maps: one business at a time ----------
async function mapsPlace(tab) {
  if (!tab || !/^https:\/\/(www\.)?google\.[a-z.]+\/maps/i.test(tab.url || "")) return null;
  $("mapscard").style.display = "block";
  const p = await runInPage(tab, "naMapsPlace");
  if (!p || !p.name) {
    $("mapsinfo").textContent = "Click one business in the list so its details panel opens.";
    $("mapscheck").disabled = true;
    return null;
  }
  $("mapsinfo").textContent = p.website ? `${p.name} - ${p.website.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]}`
                                        : `${p.name} - no website listed (a lead for a brand-new site!)`;
  $("mapsinfo").className = p.website ? "yes" : "no";
  $("mapscheck").disabled = !p.website;
  return p;
}

$("mapscheck").addEventListener("click", async () => {
  const tab = await activeTab();
  const p = await mapsPlace(tab);
  if (!p || !p.website) return;
  if (!(await refreshApp())) {
    await setList((await getList()).concat([p]));
    $("mapsres").textContent = "App isn't open, so it was saved to the list below.";
    return;
  }
  $("mapscheck").disabled = true;
  $("mapsres").textContent = "Checking the website...";
  try {
    const r = await fetch(APP + "/check", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ item: p }) });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || r.status);
    $("mapsres").innerHTML = res.is_wix
      ? `<b class="yes">✔ Wix site - saved as a ${res.level} lead (score ${res.score})</b>`
      : `<span class="no">✖ Not Wix (${res.status}). Saved anyway.</span>`;
  } catch (e) {
    $("mapsres").textContent = "Check failed: " + e.message;
  } finally {
    $("mapscheck").disabled = false;
  }
});

// ---------- Send saved list ----------
$("send").addEventListener("click", async () => {
  const list = await getList();
  if (!list.length) return msg("The saved list is empty.", false);
  if (!(await refreshApp())) return msg("Open WixLeadBot.exe first, then press Send again.", false);
  try {
    const res = await sendToApp(list);
    await setList([]);
    msg(`Sent ${res.received} websites to the app (${res.new} new).`);
  } catch (e) {
    msg("Sending failed: " + e.message, false);
  }
});

// ---------- Download as .txt (for "Use my own list of websites") ----------
$("download").addEventListener("click", async () => {
  const list = await getList();
  if (!list.length) return msg("The saved list is empty.", false);
  const lines = list.map((x) => `${x.website}, ${(x.name || "").replace(/,/g, " ")}`);
  const blob = new Blob([lines.join("\r\n") + "\r\n"], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 10);
  await chrome.downloads.download({ url, filename: `captured-websites-${stamp}.txt`, saveAs: true });
  msg(`Downloaded ${list.length} websites.`);
});

$("clear").addEventListener("click", async () => {
  await setList([]);
  msg("Saved list cleared.");
});

// ---------- Start ----------
(async () => {
  const tab = await activeTab();
  $("count").textContent = (await getList()).length;
  checkWix(tab);
  refreshApp();
  mapsPlace(tab).catch(() => {});
  if (tab && /yellowpages\.(com|ca)/i.test(tab.url || "")) {
    $("pageinfo").textContent = "Yellow Pages detected. Click Capture.";
    $("pageinfo").className = "yes";
  }
})();
