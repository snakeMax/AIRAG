// Settings -> Appearance -> "Buttons shown": hides tool buttons the user doesn't use, to keep pages tidy.
const SELECTORS = {
  summarize: "[data-act=sum-article],[data-act=sum-results]",
  regenerate: "[data-act=regenerate],[data-act=versions]",
  interactive: "#interBtn",
  results: ".a-actions [data-act=results]",
  more_sources: "[data-act=more-sources]",
  save: "#saveBtn",
  copy: ".a-actions [data-act=copy]",
  translate: "#trArtBtn,#trResBtn",
  listen: "#ttsBtn,#ttsStop",
  pin: "#pinBtn",
  export: "[data-act=export-html]",
  summary_file: "[data-act=sum-file],#sheet [data-file]",
  source_summarize: "[data-act=sum-source]",
  source_save: "[data-act=save-source]",
  source_pin: "[data-act=pin-source]",
  to_notes: "[data-act=to-notes],[data-act=results-to-notes]",
  source_to_notes: "[data-act=source-to-notes]",
};

// the article tool groups, and which buttons are in them: a group whose buttons are all hidden hides too
const GROUPS = { export: ["export", "copy", "summary_file", "save", "to_notes"], rewrite: ["regenerate", "translate", "summarize"],
                 sources: ["more_sources", "results"] };

export function applyButtons(buttons = {}) {
  const hide = Object.entries(SELECTORS).filter(([k]) => buttons[k] === false).map(([, sel]) => sel);
  for (const [g, keys] of Object.entries(GROUPS))
    if (keys.every(k => buttons[k] === false) && g !== "sources") hide.push(`.a-group[data-group=${g}]`);
  let el = document.getElementById("hiddenButtons");
  if (!el) { el = document.createElement("style"); el.id = "hiddenButtons"; document.head.appendChild(el); }
  el.textContent = hide.length ? `${hide.join(",")}{display:none!important}` : "";
}
