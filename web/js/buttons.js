// Settings -> Appearance -> "Buttons shown": hides tool buttons the user doesn't use, to keep pages tidy.
const SELECTORS = {
  summarize: "[data-act=sum-article],[data-act=sum-results]",
  interactive: "#interBtn",
  results: ".a-actions [data-act=results]",
  more_sources: "[data-act=more-sources]",
  save: "#saveBtn",
  copy: ".a-actions [data-act=copy]",
  translate: "#trArtBtn,#trResBtn",
  listen: "#ttsBtn,#ttsStop",
  pin: "#pinBtn",
  export: "[data-act=export-html]",
  source_summarize: "[data-act=sum-source]",
  source_save: "[data-act=save-source]",
  source_pin: "[data-act=pin-source]",
};

export function applyButtons(buttons = {}) {
  const hide = Object.entries(SELECTORS).filter(([k]) => buttons[k] === false).map(([, sel]) => sel);
  let el = document.getElementById("hiddenButtons");
  if (!el) { el = document.createElement("style"); el.id = "hiddenButtons"; document.head.appendChild(el); }
  el.textContent = hide.length ? `${hide.join(",")}{display:none!important}` : "";
}
