/* <lumen-header> — the app bar.
 *
 * Logo + brand name on the inline-start side, controls on the inline-end side.
 * The logo is the SVG mark from /brand/logo.svg inlined so it can take the theme
 * colour (--logo-tile). Brand and logo are English-only by design; every other
 * string is a data-i18n key, so a language change re-labels the bar in place.
 * Directional icons carry class "mirror" and flip in RTL (see style.css).
 *
 * The element renders into the light DOM on purpose: app.js and the tests find
 * the controls by id, and the page's CSS applies without any shadow plumbing.
 */
(function () {
  "use strict";

  // keep in step with web/brand/logo.svg (tests/test_brand.py checks the paths)
  const LOGO = '<svg class="logo" viewBox="0 0 512 512" width="30" height="30" aria-hidden="true" focusable="false">'
    + '<rect width="512" height="512" rx="112" style="fill:var(--logo-tile,#1D4ED8)"/>'
    + '<path d="M226 316 L 132 118 Q 256 66 380 118 L 286 316 Z" fill="#F59E0B"/>'
    + '<path d="M240 306 L 176 128 Q 256 100 336 128 L 272 306 Z" fill="#FCD34D"/>'
    + '<path d="M222 138 H 290 Q 316 138 316 164 V 186 Q 316 212 290 212 H 252 L 226 240 L 230 212 H 222 Q 196 212 196 186 V 164 Q 196 138 222 138 Z" fill="#F8FAFC"/>'
    + '<path d="M64 358 L256 412 L448 358 L448 380 L256 436 L64 380 Z" fill="#F8FAFC" opacity=".55"/>'
    + '<path d="M256 414 L 76 364 L 76 258 Q 76 246 90 250 L 256 306 Z" fill="#F8FAFC"/>'
    + '<path d="M256 414 L 436 364 L 436 258 Q 436 246 422 250 L 256 306 Z" fill="#DBEAFE"/>'
    + '<path d="M256 306 L 256 414" stroke="#1D4ED8" stroke-width="6" stroke-linecap="round" fill="none" opacity=".35"/>'
    + '</svg>';

  const SPEEDS = ["0.5", "0.6", "0.7", "0.8", "0.9", "1", "1.1", "1.2", "1.3", "1.4", "1.5"];

  const SPEED_OPTIONS = SPEEDS.map((s) => `<option value="${s}">${s}×</option>`).join("");

  const TEMPLATE = `
  <header class="bar">
    <div class="bar-start">
      <a class="brand" href="/" data-i18n-attr="aria-label:header.home">
        ${LOGO}<span class="brand-name" translate="no" lang="en" dir="ltr">LumenRead</span>
      </a>
      <h1 id="docTitle" class="doc-title" dir="auto" hidden></h1>
    </div>
    <div class="bar-end" role="toolbar" data-i18n-attr="aria-label:header.toolbar">
      <label class="file">
        <input type="file" id="fileInput" accept=".pdf,.txt,.md,.markdown,.html,.htm,.epub" hidden>
        <span data-i18n="header.open"></span>
      </label>
      <button id="voiceBtn" class="ghost" type="button">
        <span data-i18n="header.voice"></span> <span id="voiceNow" class="pill pill-wide" dir="auto">—</span>
      </button>
      <select id="speed" dir="ltr" data-i18n-attr="title:header.speed;aria-label:header.speed">
        ${SPEED_OPTIONS}
      </select>
      <select id="unit" data-i18n-attr="title:header.unit;aria-label:header.unit">
        <option value="paragraph" data-i18n="header.unit_paragraph"></option>
        <option value="sentence" data-i18n="header.unit_sentence"></option>
      </select>
      <button id="zhToggle" class="ghost" type="button" aria-pressed="true"
        data-i18n-attr="title:header.translation_tip"><span id="trLabel" data-i18n="header.translation"></span></button>
      <button id="vocabBtn" class="ghost" type="button">
        <span data-i18n="header.vocab"></span> <span id="vocabCount" class="pill">0</span>
      </button>
      <button id="writeBtn" class="ghost" type="button" data-i18n="header.write"></button>
      <button id="talkBtn" class="ghost" type="button" data-i18n="header.talk" hidden></button>
      <select id="langSwitch" class="lang-switch" data-i18n-attr="title:lang.switch;aria-label:lang.switch">
        <option value="system" data-i18n="lang.system"></option>
        <option value="en" lang="en" dir="ltr" data-i18n="lang.en"></option>
        <option value="ar" lang="ar" dir="rtl" data-i18n="lang.ar"></option>
      </select>
      <button id="themeToggle" class="ghost icon-btn" type="button"
        data-i18n-attr="title:header.theme;aria-label:header.theme">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M12 3a9 9 0 1 0 0 18V3z"/><circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
      </button>
      <button id="settingsBtn" class="ghost icon-btn" type="button"
        data-i18n-attr="title:header.settings;aria-label:header.settings">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="8" cy="17" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
      </button>
    </div>
  </header>`;

  class LumenHeader extends HTMLElement {
    connectedCallback() {
      if (this.dataset.ready) return;
      this.dataset.ready = "1";
      this.innerHTML = TEMPLATE;
      if (window.LumenI18n) window.LumenI18n.apply(this);
    }
  }
  if (!customElements.get("lumen-header")) customElements.define("lumen-header", LumenHeader);
})();
