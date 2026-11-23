// Runs inside the page you are viewing (only when you click a button).
// Defines naExtract() which reads business listings from the current page.
// Works on yellowpages.com and yellowpages.ca, with a general fallback for
// other directory pages (BBB, chamber of commerce lists, etc.).

/* eslint-disable no-var */
var naExtract = function () {
  var SKIP = /(^|\.)(yellowpages\.(com|ca)|yp\.(com|ca)|ypcdn\.com|ypg\.com|facebook\.com|instagram\.com|twitter\.com|x\.com|linkedin\.com|youtube\.com|youtu\.be|tiktok\.com|pinterest\.com|google\.[a-z.]+|goo\.gl|g\.page|yelp\.(com|ca)|bbb\.org|apple\.com|bing\.com|mapquest\.com|waze\.com|thryv\.com|hibu\.com|dexknows\.com|superpages\.com|localsearch\.com|doubleclick\.net|googleadservices\.com|cloudflare\.com|wix\.com|sitescout\.com|canada411\.ca|411\.ca|zocdoc\.com|healthgrades\.com|opentable\.(com|ca)|grubhub\.com|doordash\.com|ubereats\.com|seamless\.com|angi\.com|homeadvisor\.com|houzz\.com|nextdoor\.com|tripadvisor\.[a-z.]+|booking\.com|expedia\.[a-z.]+)$/i;

  function hostOf(u) {
    try { return new URL(u).hostname.replace(/^www\./i, "").toLowerCase(); } catch (e) { return ""; }
  }

  // Turn a link into the real business website (follows redirect links like /gourl?url=...)
  function realUrl(href) {
    if (!href || /^(mailto|tel|javascript):/i.test(href)) return null;
    var u;
    try { u = new URL(href, location.href); } catch (e) { return null; }
    if (!/^https?:$/.test(u.protocol)) return null;
    if (u.hostname !== location.hostname) return u.href;
    var found = null;
    u.searchParams.forEach(function (v) {
      if (found) return;
      var d = v;
      try { d = decodeURIComponent(v); } catch (e) { /* keep v */ }
      if (/^https?:\/\//i.test(d)) found = d;
      else if (/^(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(\/|$)/i.test(d) && !/\s/.test(d)) found = "http://" + d;
    });
    return found;
  }

  function text(el) { return el ? (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : ""; }

  var CARD_SEL = [
    "div.result", "div.srp-listing", ".v-card",                 // yellowpages.com
    ".listing", ".listing__content", "[class*='listing__']",     // yellowpages.ca
    "article", "li", "[class*='result']", "[class*='listing']", "[class*='card']"
  ].join(",");
  var NAME_SEL = "a.business-name, .business-name, .listing__name, .listing__name--link, [class*='business-name'], [class*='listing__name'], h2, h3, h4";
  var PHONE_SEL = ".phones, .phone, [class*='phone'], a[href^='tel:']";
  var ADDR_SEL = ".adr, .street-address, .locality, .listing__address, [class*='address'], address";

  // Page context: state / province and category from the URL
  var pageRegion = "", pageCategory = "";
  var host = location.hostname.replace(/^www\./, "");
  var path = decodeURIComponent(location.pathname);
  var m;
  if (/yellowpages\.com$/.test(host)) {
    // /dallas-tx/dentists   or   /search?search_terms=dentists&geo_location_terms=Dallas%2C+TX
    m = path.match(/^\/[a-z0-9-]+-([a-z]{2})\/([^/]+)/i);
    if (m) { pageRegion = "US-" + m[1].toUpperCase(); pageCategory = m[2]; }
    var qs = new URLSearchParams(location.search);
    if (qs.get("search_terms")) pageCategory = qs.get("search_terms");
    var geo = qs.get("geo_location_terms") || "";
    m = geo.match(/,\s*([A-Za-z]{2})\b/);
    if (m) pageRegion = "US-" + m[1].toUpperCase();
  } else if (/yellowpages\.ca$/.test(host)) {
    // /search/si/1/dentist/Toronto+ON
    m = path.match(/\/search\/[a-z]+\/\d+\/([^/]+)\/([^/]+)/i);
    if (m) {
      pageCategory = m[1].replace(/\+/g, " ");
      var p = m[2].replace(/\+/g, " ").match(/\b(AB|BC|MB|NB|NL|NS|ON|PE|QC|SK|NT|NU|YT)\b/i);
      if (p) pageRegion = "CA-" + p[1].toUpperCase();
    }
  }

  var seen = {}, items = [];
  var links = document.querySelectorAll("a[href]");
  for (var i = 0; i < links.length; i++) {
    var a = links[i];
    var url = realUrl(a.getAttribute("href"));
    if (!url) continue;
    var h = hostOf(url);
    if (!h || SKIP.test(h) || h === host || seen[h]) continue;

    var card = a.closest(CARD_SEL) || a.parentElement;
    // climb a little so the card includes the name and phone
    for (var up = 0; up < 3 && card && card.parentElement && !card.querySelector(NAME_SEL); up++) {
      card = card.parentElement;
    }
    var nameEl = card ? card.querySelector(NAME_SEL) : null;
    var name = text(nameEl);
    if (!name && /website|visit/i.test(text(a)) === false) name = text(a);
    var phoneEl = card ? card.querySelector(PHONE_SEL) : null;
    var phone = phoneEl ? (phoneEl.getAttribute("href") || "").replace(/^tel:/i, "") || text(phoneEl) : "";
    var addrEl = card ? card.querySelector(ADDR_SEL) : null;       // outermost address block
    var locEl = card ? card.querySelector(".locality") : null;
    var addrText = addrEl ? Array.prototype.map.call(addrEl.children.length ? addrEl.children : [addrEl], text)
                                .filter(Boolean).join(", ") : "";

    seen[h] = true;
    items.push({
      name: name.slice(0, 150),
      website: url.split("#")[0],
      phone: phone.slice(0, 40),
      address: addrText.slice(0, 200),
      city: (locEl ? text(locEl) : addrText).slice(0, 120),
      region: pageRegion,
      category: pageCategory,
      found_on: location.href.split("#")[0]
    });
  }
  return { page: location.hostname, region: pageRegion, category: pageCategory, items: items };
};

// Is the current page a Wix website?
var naIsWix = function () {
  var html = document.documentElement.outerHTML;
  return html.indexOf("static.wixstatic.com") >= 0 ||
         html.indexOf("static.parastorage.com") >= 0 ||
         html.indexOf('content="Wix.com Website Builder"') >= 0;
};

// Google Maps: read ONLY the one business you have open (a place page), when you
// click the button. It never reads search result lists or scrolls for you.
var naMapsPlace = function () {
  if (!/(^|\.)google\.[a-z.]+$/i.test(location.hostname) || location.pathname.indexOf("/maps") !== 0) return null;
  function text(el) { return el ? (el.textContent || "").replace(/\s+/g, " ").trim() : ""; }
  var main = document.querySelector('[role="main"][aria-label]') || document;
  var name = text(main.querySelector("h1")) || (main.getAttribute && main.getAttribute("aria-label")) || "";
  var site = main.querySelector('a[data-item-id="authority"]') ||
             Array.prototype.find.call(main.querySelectorAll("a[aria-label]"), function (a) {
               return /^website:/i.test(a.getAttribute("aria-label") || "");
             });
  var href = site ? site.href : "";
  try {   // Google sometimes wraps the link: /url?q=https://...
    var u = new URL(href);
    if (/google\./.test(u.hostname) && (u.searchParams.get("q") || u.searchParams.get("url"))) {
      href = u.searchParams.get("q") || u.searchParams.get("url");
    }
  } catch (e) { href = ""; }
  var phoneBtn = main.querySelector('button[data-item-id^="phone"]');
  var phone = phoneBtn ? (phoneBtn.getAttribute("data-item-id") || "").replace(/^phone:tel:/, "") : "";
  var addrBtn = main.querySelector('button[data-item-id="address"]');
  var address = addrBtn ? (addrBtn.getAttribute("aria-label") || text(addrBtn)).replace(/^Address:\s*/i, "") : "";
  var catBtn = main.querySelector('button[jsaction*="category"]');
  return {
    name: name.slice(0, 200), website: href, phone: phone.slice(0, 40), address: address.slice(0, 200),
    city: address.slice(0, 120), category: text(catBtn).slice(0, 60) || "google maps",
    found_on: location.href.split("?")[0].slice(0, 300)
  };
};
