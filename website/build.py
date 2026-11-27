"""Render the self-contained Fire Tools guide for a GitHub Pages project URL."""

import argparse
import re
import shutil
import tomllib
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path
from string import Template


ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/dev1niscool/fire-tools"
GROUPS = ("Get started", "Tool guides", "Project")


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    intro: str
    icon: str
    group: str
    keywords: str

    @property
    def url(self):
        return f"{self.slug}.html"


PAGES = (
    Page("index", "Overview", "A field guide to setting up and managing Amazon Fire tablets.", "book", "Get started", "start home documentation"),
    Page("setup", "Setup", "Install Fire Tools on your computer and connect your tablet over USB.", "plug", "Get started", "install launcher windows linux demo adb driver usb debugging developer options"),
    Page("compatibility", "Compatibility", "Find your tablet generation, Fire OS version and the right guide for your device.", "tablet", "Get started", "model generation firmware update android api hd 10 hd 8 max 11 fire 7 8.3.3.8"),
    Page("google-play", "Google Play", "Choose the right APKs, verify their signatures and install Google Play.", "play", "Tool guides", "store apps apks download account manager framework services calendar contacts signing hash"),
    Page("ads", "Lock-screen ads", "Review the options for Special Offers on your Fire OS version.", "lock", "Tool guides", "lockscreen lock screen ads ad removal advertisements offers restore helper firmware"),
    Page("apps", "Amazon apps", "Choose which preinstalled apps to disable and restore them when you need them.", "grid", "Tool guides", "debloat bloatware packages presets uninstall remove restore apps"),
    Page("tools", "More tools", "Use the tool catalog for files, backups, screenshots and device settings.", "sliders", "Tool guides", "backup restore keyboard launcher wifi files recording profiles permissions screenshot"),
    Page("resources", "Source & safety", "Inspect the code, read the audit and find the original project references.", "code", "Project", "github security malware viruses privacy trust license resources xda forum issue source code"),
)
BY_SLUG = {page.slug: page for page in PAGES}


def icon(name, size=20):
    return (f'<svg class="icon" width="{size}" height="{size}" aria-hidden="true" '
            f'focusable="false"><use href="assets/icons.svg#{name}"></use></svg>')


def nav(page, mobile=False):
    sections = []
    for group in GROUPS:
        links = []
        for item in (item for item in PAGES if item.group == group):
            current = ' aria-current="page"' if page == item else ""
            links.append(f'<a href="{item.url}"{current}>{icon(item.icon, 18)}<span>{escape(item.title)}</span></a>')
        sections.append(f'<div class="nav-group"><p>{group}</p>{"".join(links)}</div>')
    name = "Mobile guide" if mobile else "Guide"
    return f'<nav aria-label="{name}" class="page-links">{"".join(sections)}</nav>'


def guide_card(slug, text, color):
    page = BY_SLUG[slug]
    return (f'<a class="guide-card {color}" href="{page.url}">'
            f'<span class="tile-icon">{icon(page.icon, 24)}</span>'
            f'<h3>{escape(page.title)}</h3><p>{escape(text)}</p>'
            f'<span class="card-arrow">{icon("arrow", 18)}</span></a>')


def overview():
    template = Template((ROOT / "overview.html").read_text(encoding="utf-8"))
    return template.substitute(
        arrow=icon("arrow", 17), terminal=icon("terminal", 15), check=icon("check", 17),
        shield=icon("shield", 22),
        cards="".join((
            guide_card("google-play", "Verify and install the Play Store and Google services.", "blue"),
            guide_card("ads", "Manage Special Offers on supported firmware.", "violet"),
            guide_card("apps", "Disable preinstalled apps and restore your changes.", "mint"),
        )),
    )


def section_heading(match):
    title = match.group(1)
    token = re.sub(r"[^a-z0-9]+", "-", unescape(title).lower()).strip("-")
    return f'<h2 id="{token}">{title}</h2>'


def article(page):
    fragment = (ROOT / "content" / page.url).read_text(encoding="utf-8")
    fragment = re.sub(r"<h2>([^<>]+)</h2>", section_heading, fragment)
    return (f'<article class="guide-article"><header class="article-head"><span class="article-icon">{icon(page.icon, 25)}</span>'
            f'<h1>{escape(page.title)}</h1><p>{escape(page.intro)}</p></header>{fragment}</article>')


def search_links():
    links = []
    for page in PAGES:
        terms = escape(f"{page.title} {page.intro} {page.keywords}", quote=True)
        links.append(f'<a class="search-hit" href="{page.url}" data-search="{terms}">'
                     f'{icon(page.icon, 18)}<span><strong>{escape(page.title)}</strong>'
                     f'<small>{escape(page.intro)}</small></span>{icon("arrow", 16)}</a>')
    return "".join(links)


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", output / "assets", dirs_exist_ok=True)
    template = Template((ROOT / "layout.html").read_text(encoding="utf-8"))
    version = tomllib.loads((ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for page in PAGES:
        contents = overview() if page.slug == "index" else article(page)
        variables = dict(
            browser_title="Fire Tools — Fire tablet field guide" if page.slug == "index" else f"{escape(page.title)} · Fire Tools",
            description=escape(page.intro, quote=True), title=escape(page.title), group=page.group,
            repo=REPO, version=escape(version), desktop_nav=nav(page), mobile_nav=nav(page, mobile=True),
            contents=contents, search_links=search_links(),
        )
        for name in ("github", "search", "external", "chevron", "menu", "close", "book", "shield"):
            variables[name] = icon(name, 18)
        (output / page.url).write_text(template.substitute(variables), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
