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
  const error = get("error");
  const storageKey = "fire-tools.tutorial.v1";
  const versionPattern = /^[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}$/;
  const modelNames = new Map(route.models.map((item) => [item.id, item.label]));
  const choices = new Map();
  let profile = null;
  let sections = [];
  let index = -1;

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
      new Set(value.goals).size === value.goals.length && value.goals.every((goal) => choices.has(goal));
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
    updateFirmwareField();
    for (const [goal, checkbox] of choices) checkbox.checked = value?.goals.includes(goal) || false;
    get("ads-method").value = value?.adsMethod || "amazon";
    updateAdsField();
    clearError();
  }

  function readForm() {
    const value = {
      model: model.value,
      firmware: unknown.checked ? "" : firmware.value.trim(),
      goals: [...choices].filter(([, checkbox]) => checkbox.checked).map(([goal]) => goal),
    };
    if (value.goals.includes("ads")) value.adsMethod = get("ads-method").value;
    clearError();
    if (!modelNames.has(value.model)) {
      showError(model, "Choose your tablet model, or select the option for an unknown model.");
    } else if (!unknown.checked && !versionPattern.test(value.firmware)) {
      showError(firmware, "Enter the version with dots, such as 8.3.3.8, or choose “I don’t know the version”.");
    } else if (!value.goals.length) {
      showError(choices.values().next().value, "Choose at least one task to start your tutorial.");
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

  function profileLabel() {
    const version = profile.firmware ? "Fire OS " + profile.firmware : "Fire OS version unknown";
    return modelNames.get(profile.model) + " · " + version;
  }

  function showView(hash, focus) {
    const sectionIndex = sections.findIndex((item) => hash === "#section-" + item.id);
    if (profile && hash === "#complete") {
      get("finished-profile").textContent = profileLabel();
      display(finished, get("finished-title"), focus);
    } else if (sectionIndex !== -1) {
      index = sectionIndex;
      const section = sections[index];
      const progress = get("progress");
      progress.max = sections.length;
      progress.value = index + 1;
      get("progress-label").textContent = "Section " + (index + 1) + " of " + sections.length;
      get("profile").textContent = profileLabel();
      get("title").textContent = section.title;
      get("intro").textContent = section.intro;
      const steps = section.steps.map((text) => {
        const li = document.createElement("li");
        li.textContent = text;
        return li;
      });
      get("steps").replaceChildren(...steps);
      get("check-text").textContent = section.check;
      get("check").hidden = !section.check;
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
      setForm(profile);
      display(setup, get("setup-title"), focus);
    }
    saveSession(profile ? {profile, view: hash} : null);
  }

  function navigate(hash) {
    // A history entry retains its original choices even after the user edits the guide.
    history.pushState({fireTutorial: profile}, "", hash);
    showView(hash, true);
  }

  function load(focus) {
    const state = history.state;
    const session = readSession();
    const saved = state && Object.hasOwn(state, "fireTutorial") ? state.fireTutorial : session?.profile;
    profile = validProfile(saved) ? saved : null;
    sections = profile ? route.build(profile) : [];
    let hash = location.hash;
    if (profile && !hash && (session?.view === "#complete" ||
        sections.some((section) => session?.view === "#section-" + section.id))) {
      hash = session.view;
      history.replaceState({fireTutorial: profile}, "", hash);
    }
    showView(hash, focus);
  }

  setup.addEventListener("input", clearError);
  unknown.addEventListener("change", updateFirmwareField);
  choices.get("ads").addEventListener("change", updateAdsField);
  setup.addEventListener("submit", (event) => {
    event.preventDefault();
    const selected = readForm();
    if (!selected) return;
    profile = selected;
    sections = route.build(profile);
    history.replaceState({fireTutorial: profile}, "", "#choices");
    navigate("#section-" + sections[0].id);
  });
  get("next").addEventListener("click", () =>
    navigate(index + 1 === sections.length ? "#complete" : "#section-" + sections[index + 1].id));
  get("back").addEventListener("click", () => navigate(index === 0 ? "#choices" : "#section-" + sections[index - 1].id));
  get("edit").addEventListener("click", () => navigate("#choices"));
  get("review").addEventListener("click", () => navigate("#section-" + sections[sections.length - 1].id));
  get("restart").addEventListener("click", () => {
    profile = null;
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
