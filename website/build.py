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
SITE_URL = "https://dev1niscool.github.io/fire-tools/"
GROUPS = ("Get started", "Tool guides", "Project", "Experimental")


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
    Page("tutorial", "Guided setup", "Choose your tablet, Fire OS version and goals. Follow your instructions one section at a time.", "book", "Get started", "tutorial walkthrough personalized wizard beginner step by step next model firmware Google Play ads debloat"),
    Page("browser", "Browser tools", "Connect your Fire tablet directly to desktop Chrome over USB. This experimental version runs on this page.", "plug", "Experimental", "experimental WebUSB browser only ADB Google Play install APK debloat ads animations updates DNS undo inventory"),
    Page("setup", "Setup", "Install Fire Tools on your computer and connect your tablet over USB.", "plug", "Get started", "install launcher windows linux macos demo adb driver usb debugging developer options"),
    Page("drivers", "USB drivers", "Find out whether Windows needs an ADB driver and what the driver audit verified.", "plug", "Get started", "windows 10 11 linux mac usb mtp rsa unauthorized driver installation amazon adb signature catalog dpinst xda"),
    Page("compatibility", "Tablet models", "Identify your Fire tablet generation, Android API level and processor architecture.", "tablet", "Get started", "compatibility model generation android sdk abi hd 10 hd 8 max 11 fire 7"),
    Page("firmware", "Firmware support", "Check which Fire Tools features your model and installed Fire OS build can use.", "layers", "Get started", "compatibility hd 10 8 max 11 fire 7 google play ads debloat restricted android 8.3.3.8 8.3.3.7 7.3.3.1 7.3.2.2 5.3.7.3 5.3.6.4 5.3.6.2 firmware updates"),
    Page("google-play", "Google Play", "Choose the right APKs, verify their signatures and install Google Play.", "play", "Tool guides", "store apps apks download account manager framework services calendar contacts signing hash"),
    Page("ads", "Lock-screen ads", "Review the options for Special Offers on your Fire OS version.", "lock", "Tool guides", "lockscreen lock screen ads ad removal advertisements offers restore helper firmware"),
    Page("apps", "Amazon apps", "Choose which preinstalled apps to disable and restore them when you need them.", "grid", "Tool guides", "debloat bloatware packages presets uninstall remove restore apps"),
    Page("updates", "System updates", "Check, disable and restore the firmware updater packages on your tablet.", "layers", "Tool guides", "ota update updates firmware stop prevent block restore security patches 8.3.3.8"),
    Page("animations", "Animation speed", "Make menus and transitions feel quicker using your tablet’s Developer Options.", "speed", "Tool guides", "faster speed up performance snappy animations scales 0.5x 0.5× 1x drawing animator duration window transition developer options"),
    Page("tools", "More tools", "Use the tool catalog for files, backups, screenshots and device settings.", "sliders", "Tool guides", "backup restore keyboard launcher wifi files recording profiles permissions screenshot"),
    Page("apkmirror", "APKMirror audit", "Compare the Google APKs used by Toolbox v46 and verify the files you download.", "shield", "Project", "apk mirror apkmirror audit malware virus safety signatures hash sha256 google lineage rea catalog xda offline verify"),
    Page("resources", "Source & safety", "Inspect the code, read the audit and find the original project references.", "code", "Project", "github security malware viruses privacy trust license resources xda forum issue source code"),
)
BY_SLUG = {page.slug: page for page in PAGES}


PAGE_ASSETS = {
    "tutorial": '<link rel="stylesheet" href="assets/tutorial.css">\n'
                '  <script defer src="assets/tutorial-route.js"></script>\n'
                '  <script defer src="assets/tutorial.js"></script>',
    "browser": '<link rel="stylesheet" href="assets/browser-tools.css">\n'
               '  <script type="module" src="assets/browser-ui.mjs"></script>',
}
# The USB interface and the local APK reader need no network connection.
BROWSER_POLICY = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
                  "script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; manifest-src 'self'; connect-src 'none'")


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
    shutil.copyfile(ROOT / "site.webmanifest", output / "site.webmanifest")
    template = Template((ROOT / "layout.html").read_text(encoding="utf-8"))
    version = tomllib.loads((ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for page in PAGES:
        contents = overview() if page.slug == "index" else article(page)
        variables = dict(
            browser_title="Fire Tools — Fire tablet field guide" if page.slug == "index" else f"{escape(page.title)} · Fire Tools",
            site_url=SITE_URL, canonical_url=SITE_URL if page.slug == "index" else SITE_URL + page.url,
            share_image_alt="Fire Tools, a field guide for Amazon Fire tablets, beside a tablet displaying blue contour lines.",
            description=escape(page.intro, quote=True), title=escape(page.title), group=page.group,
            repo=REPO, version=escape(version), desktop_nav=nav(page), mobile_nav=nav(page, mobile=True),
            contents=contents, search_links=search_links(),
            page_assets=PAGE_ASSETS.get(page.slug, ""),
            page_policy=(f'<meta http-equiv="Content-Security-Policy" content="{BROWSER_POLICY}">\n'
                         '  <meta name="referrer" content="no-referrer">' if page.slug == "browser" else ""),
        )
        for name in ("github", "search", "external", "chevron", "menu", "close", "book", "shield"):
            variables[name] = icon(name, 18)
        (output / page.url).write_text(template.substitute(variables), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
