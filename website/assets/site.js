(() => {
  const dialog = document.querySelector("#search-dialog");
  const trigger = document.querySelector(".search-trigger");
  const input = document.querySelector("#guide-search");
  const hits = [...dialog.querySelectorAll(".search-hit")];
  const empty = dialog.querySelector(".empty-result");
  const menu = document.querySelector(".mobile-menu");

  function filter() {
    const words = input.value.toLowerCase().trim().split(/\s+/);
    for (const hit of hits) {
      const haystack = hit.dataset.search.toLowerCase();
      hit.hidden = !words.every((word) => haystack.includes(word));
    }
    empty.hidden = hits.some((hit) => !hit.hidden);
  }

  function openSearch() {
    menu.open = false;
    if (!dialog.open) dialog.showModal();
    input.value = "";
    filter();
    input.focus();
  }

  if (typeof dialog.showModal === "function") {
    trigger.hidden = false;
    if (/Mac|iPhone|iPad/.test(navigator.platform))
      trigger.querySelector("kbd").textContent = "⌘ K";
    trigger.addEventListener("click", openSearch);
    dialog
      .querySelector(".close-search")
      .addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (
        event.clientX < box.left ||
        event.clientX > box.right ||
        event.clientY < box.top ||
        event.clientY > box.bottom
      )
        dialog.close();
    });
    input.addEventListener("input", filter);
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        dialog.close();
        return;
      }
      const visible = hits.filter((hit) => !hit.hidden);
      if (!visible.length) return;
      const index = visible.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next =
          event.key === "ArrowDown"
            ? (index + 1) % visible.length
            : index <= 0
              ? visible.length - 1
              : index - 1;
        visible[next].focus();
      } else if (event.key === "Enter" && document.activeElement === input) {
        event.preventDefault();
        visible[0].click();
      }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openSearch();
      }
    });
  }
  document.addEventListener("click", (event) => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.open) {
      menu.open = false;
      menu.querySelector("summary").focus();
    }
  });
})();
