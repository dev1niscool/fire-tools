(() => {
  const tutorial = document.getElementById("tutorial");
  const route = window.FireTutorialRoute;
  if (!tutorial || !route) return;

  const get = (id) => document.getElementById("tutorial-" + id);
  const setup = get("setup");
  const reader = get("reader");
  const finished = get("finished");
  const model = get("model");
  const firmware = get("firmware");
  const unknown = get("unknown");
  const confirmation = get("confirm-version");
  const error = get("error");
  const storageKey = "fire-tools.tutorial.v1";
  const versionPattern = /^[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}$/;
  const modelNames = new Map(route.models.map((item) => [item.id, item.label]));
  const choices = new Map();
  let profile = null;
  let sections = [];
  let index = -1;
  let firmwareConfirmed = false;

  for (const item of route.models) model.add(new Option(item.label, item.id));
  for (const goal of route.goals) {
    const card = document.createElement("label");
    const checkbox = document.createElement("input");
    const copy = document.createElement("span");
    const title = document.createElement("strong");
    const description = document.createElement("small");
    card.className = "tutorial-goal";
    checkbox.type = "checkbox";
    checkbox.name = "goals";
    checkbox.value = goal.id;
    checkbox.id = "tutorial-goal-" + goal.id;
    title.id = checkbox.id + "-title";
    title.textContent = goal.label;
    description.id = checkbox.id + "-help";
    description.textContent = goal.description;
    checkbox.setAttribute("aria-labelledby", title.id);
    checkbox.setAttribute("aria-describedby", description.id);
    copy.append(title, description);
    card.append(checkbox, copy);
    get("goals").append(card);
    if (goal.id === "ads") checkbox.setAttribute("aria-controls", "tutorial-ads-options");
    choices.set(goal.id, checkbox);
  }

  function validProfile(value) {
    return value && modelNames.has(value.model) &&
      (value.adsMethod === undefined || value.adsMethod === "amazon" || value.adsMethod === "tool") &&
      typeof value.firmware === "string" && value.firmware.length <= firmware.maxLength &&
      (!value.firmware || versionPattern.test(value.firmware)) &&
      Array.isArray(value.goals) && value.goals.length > 0 && value.goals.length <= choices.size &&
      new Set(value.goals).size === value.goals.length && value.goals.every((goal) => choices.has(goal)) &&
      (!value.goals.includes("firmware-8337") || route.firmwareUpdateStatus(value.model, value.firmware) === "available");
  }

  function readSession() {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey));
    } catch {
      return null;
    }
  }

  function saveSession(value) {
    try {
      if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
      else sessionStorage.removeItem(storageKey);
    } catch {
      // Navigation still works when this browser disallows storage.
    }
  }

  function clearError() {
    error.hidden = true;
    const control = setup.querySelector('[aria-invalid="true"]');
    if (control) {
      control.removeAttribute("aria-invalid");
      control.setAttribute("aria-describedby", control.getAttribute("aria-describedby").split(" ")[0]);
    }
  }

  function showError(control, message) {
    const field = control.closest(".tutorial-field");
    if (field) field.append(error);
    else get("goals").before(error);
    control.setAttribute("aria-describedby", control.getAttribute("aria-describedby") + " " + error.id);
    error.textContent = message;
    error.hidden = false;
    control.setAttribute("aria-invalid", "true");
    control.focus();
  }

  function updateFirmwareField() {
    firmware.disabled = unknown.checked;
    firmware.required = !unknown.checked;
    const checkbox = choices.get("firmware-8337");
    const status = route.firmwareUpdateStatus(model.value, unknown.checked ? "" : firmware.value.trim());
    const descriptions = {
      available: "Start with the manual USB update before your other tasks.",
      installed: "Your tablet already runs Fire OS 8.3.3.7. You can go straight to your other tasks.",
      newer: "Your tablet runs a newer version. This package cannot downgrade it.",
      unknown: "Enter the full four-part Fire OS 8 version to check eligibility.",
      other: "Available for the Fire HD 10 (2023, 13th generation) on an earlier Fire OS 8 build.",
    };
    checkbox.disabled = status !== "available";
    if (checkbox.disabled) checkbox.checked = false;
    document.getElementById(checkbox.id + "-help").textContent = descriptions[status];
  }

  function updateAdsField() {
    const show = choices.get("ads").checked;
    get("ads-options").hidden = !show;
    get("ads-method").disabled = !show;
  }

  function setForm(value) {
    model.value = value?.model || "";
    firmware.value = value?.firmware || "";
    unknown.checked = Boolean(value && !value.firmware);
    for (const [goal, checkbox] of choices) checkbox.checked = value?.goals.includes(goal) || false;
    updateFirmwareField();
    get("ads-method").value = value?.adsMethod || "amazon";
    updateAdsField();
    clearError();
  }

  function readForm() {
    const value = {
      model: model.value,
      firmware: unknown.checked ? "" : firmware.value.trim(),
      goals: [...choices].filter(([, checkbox]) => checkbox.checked && !checkbox.disabled).map(([goal]) => goal),
    };
    if (value.goals.includes("ads")) value.adsMethod = get("ads-method").value;
    clearError();
    if (!modelNames.has(value.model)) {
      showError(model, "Choose your tablet model, or select the option for an unknown model.");
    } else if (!unknown.checked && !versionPattern.test(value.firmware)) {
      showError(firmware, "Enter the version with dots, such as 8.3.3.8, or choose “I don’t know the version”.");
    } else if (!value.goals.length) {
      showError(get("goals").querySelector("input:enabled"), "Choose at least one task to start your tutorial.");
    } else {
      return value;
    }
    return null;
  }

  function display(view, heading, focus) {
    for (const item of [setup, reader, finished]) item.hidden = item !== view;
    if (focus) {
      heading.focus({preventScroll: true});
      view.scrollIntoView({block: "start"});
    }
  }

  function profileLabel(afterUpdate) {
    let version = profile.firmware ? "Fire OS " + profile.firmware : "Fire OS version unknown";
    if (profile.goals.includes("firmware-8337")) {
      version = afterUpdate ? "Fire OS 8.3.3.7" : "Starting version · Fire OS " + profile.firmware;
    }
    return modelNames.get(profile.model) + " · " + version;
  }

  function historyState() {
    return {fireTutorial: profile, firmwareConfirmed};
  }

  function showView(hash, focus) {
    let sectionIndex = sections.findIndex((item) => hash === "#section-" + item.id);
    const confirmIndex = sections.findIndex((item) => item.id === "fw8337-confirm");
    if (confirmIndex !== -1 && !firmwareConfirmed && (hash === "#complete" || sectionIndex > confirmIndex)) {
      sectionIndex = confirmIndex;
      hash = "#section-fw8337-confirm";
      history.replaceState(historyState(), "", hash);
    }
    if (profile && hash === "#complete") {
      get("finished-profile").textContent = profileLabel(firmwareConfirmed);
      display(finished, get("finished-title"), focus);
    } else if (sectionIndex !== -1) {
      index = sectionIndex;
      const section = sections[index];
      const progress = get("progress");
      progress.max = sections.length;
      progress.value = index + 1;
      get("progress-label").textContent = "Section " + (index + 1) + " of " + sections.length;
      get("profile").textContent = profileLabel(confirmIndex !== -1 && sectionIndex > confirmIndex);
      get("title").textContent = section.title;
      get("intro").textContent = section.intro;
      const steps = section.steps.map((text) => {
        const li = document.createElement("li");
        li.textContent = text;
        return li;
      });
      get("steps").replaceChildren(...steps);
      get("check-text").textContent = section.check;
      const confirming = sectionIndex === confirmIndex;
      get("check").hidden = !section.check && !confirming;
      get("confirm-label").hidden = !confirming;
      confirmation.checked = firmwareConfirmed;
      get("next").disabled = confirming && !firmwareConfirmed;
      const links = section.links.map(({label, href}) => {
        const link = document.createElement("a");
        link.href = href;
        link.textContent = label;
        return link;
      });
      get("links").replaceChildren(...links);
      get("links").hidden = !links.length;
      get("next").querySelector("span").textContent = index + 1 === sections.length ? "Finish tutorial" : "Next";
      display(reader, get("title"), focus);
    } else {
      hash = "#choices";
      index = -1;
      const updated = firmwareConfirmed && profile?.goals.includes("firmware-8337");
      setForm(updated ? {...profile, firmware: "8.3.3.7"} : profile);
      display(setup, get("setup-title"), focus);
    }
    saveSession(profile ? {profile, view: hash, firmwareConfirmed} : null);
  }

  function navigate(hash) {
    // A history entry retains its original choices even after the user edits the guide.
    history.pushState(historyState(), "", hash);
    showView(hash, true);
  }

  function load(focus) {
    const state = history.state;
    const session = readSession();
    const hasHistoryProfile = state && Object.hasOwn(state, "fireTutorial");
    const saved = hasHistoryProfile ? state.fireTutorial : profile || session?.profile;
    // The latest choice for this run also applies when revisiting an older history entry.
    const sameRun = typeof saved?.updateRun === "string" && saved.updateRun === profile?.updateRun;
    const storedRun = typeof saved?.updateRun === "string" && saved.updateRun === session?.profile?.updateRun;
    if (!sameRun) firmwareConfirmed = (storedRun ? session?.firmwareConfirmed : state?.firmwareConfirmed) === true;
    profile = validProfile(saved) ? saved : null;
    sections = profile ? route.build(profile) : [];
    let hash = location.hash;
    if (profile && !hash && (session?.view === "#complete" ||
        sections.some((section) => session?.view === "#section-" + section.id))) {
      hash = session.view;
    }
    if (profile && (!hasHistoryProfile || hash !== location.hash)) history.replaceState(historyState(), "", hash);
    showView(hash, focus);
  }

  setup.addEventListener("input", clearError);
  model.addEventListener("change", updateFirmwareField);
  firmware.addEventListener("input", updateFirmwareField);
  unknown.addEventListener("change", updateFirmwareField);
  choices.get("ads").addEventListener("change", updateAdsField);
  setup.addEventListener("submit", (event) => {
    event.preventDefault();
    const selected = readForm();
    if (!selected) return;
    profile = selected;
    firmwareConfirmed = false;
    if (profile.goals.includes("firmware-8337")) profile.updateRun = crypto.randomUUID?.() || String(Date.now());
    sections = route.build(profile);
    history.replaceState(historyState(), "", "#choices");
    navigate("#section-" + sections[0].id);
  });
  confirmation.addEventListener("change", () => {
    firmwareConfirmed = confirmation.checked;
    get("next").disabled = !firmwareConfirmed;
    history.replaceState(historyState(), "", location.hash);
    saveSession({profile, view: location.hash, firmwareConfirmed});
  });
  get("next").addEventListener("click", () =>
    navigate(index + 1 === sections.length ? "#complete" : "#section-" + sections[index + 1].id));
  get("back").addEventListener("click", () => navigate(index === 0 ? "#choices" : "#section-" + sections[index - 1].id));
  get("edit").addEventListener("click", () => navigate("#choices"));
  get("review").addEventListener("click", () => navigate("#section-" + sections[sections.length - 1].id));
  get("restart").addEventListener("click", () => {
    profile = null;
    firmwareConfirmed = false;
    sections = [];
    navigate("#choices");
  });
  // Keep the section URL when the keyboard shortcut moves focus to the page content.
  const skip = document.querySelector('.skip[href="#main"]');
  skip?.addEventListener("click", (event) => {
    if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const main = document.getElementById("main");
    main.focus({preventScroll: true});
    main.scrollIntoView({block: "start"});
  });
  window.addEventListener("popstate", () => load(true));
  load(false);
  get("fallback").hidden = true;
})();
