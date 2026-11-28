"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
require("../assets/tutorial-route.js");

const { models, goals, build, firmwareUpdateStatus } = globalThis.FireTutorialRoute;
const plan = (goals, model = "hd10-2023", firmware = "8.3.3.8", adsMethod = "amazon") => build({ model, firmware, goals, adsMethod });
const ids = sections => sections.map(section => section.id);
const words = section => [section.intro, ...section.steps, section.check].join(" ");

test("HD 10 guide prepares only chosen workflows and explains its firmware limits", () => {
    const route = plan(["debloat", "play", "ads"]);
    const steps = ids(route);
    for (const step of ["computer", "usb", "connect", "apk-tools", "play-files", "play", "ads", "debloat", "finish"]) {
        assert.ok(steps.includes(step), step);
    }
    assert.ok(steps.indexOf("apk-tools") < steps.indexOf("usb"));
    assert.ok(steps.indexOf("usb") < steps.indexOf("connect"));
    assert.ok(steps.indexOf("connect") < steps.indexOf("play-files"));
    assert.ok(steps.indexOf("play-files") < steps.indexOf("play"));
    assert.match(words(route.find(s => s.id === "play-files")), /arm64-v8a/);
    assert.match(words(route.find(s => s.id === "ads")), /8\.3\.3\.8/);
    assert.ok(!steps.some(id => ["updates", "backup", "animations", "dns", "sideload"].includes(id)));
});

test("tablet-only animations and account ad removal require no computer, even on old or unknown tablets", () => {
    for (const [model, firmware] of [["hd10-2023", "8.3.3.8"], ["hd10-2017", "5.3.7.3"], ["unknown", ""]]) {
        for (const selected of [["ads"], ["animations"], ["ads", "animations"]]) {
            const route = plan(selected, model, firmware);
            for (const id of selected) assert.ok(ids(route).includes(id));
            for (const id of ["computer", "usb", "connect", "ads-desktop", "apk-tools", "finish"]) assert.ok(!ids(route).includes(id));
        }
    }
    const ads = plan(["ads"]).find(s => s.id === "ads");
    assert.match(words(ads), /price|fee/i);
    assert.ok(ads.links.some(l => l.href.includes("amazon.com/")));
});

test("unknown, mismatched, future, or unsupported profiles never receive desktop changes", () => {
    for (const [model, firmware] of [["unknown", "8.3.3.8"], ["hd10-2023", ""], ["hd10-2023", "7.3.3.1"],
        ["hd10-2023", "9.1.0.0"], ["hd10-2017", "5.3.7.3"], ["bogus", "8.3.3.8"], ["hd10-2023", "oops"]]) {
        const route = plan(["play", "ads", "debloat", "updates", "animations", "backup"], model, firmware);
        assert.ok(ids(route).includes("eligibility"));
        for (const id of ["computer", "usb", "apk-tools", "play-files", "play", "debloat", "updates", "backup"]) {
            assert.ok(!ids(route).includes(id), model + " " + firmware + " " + id);
        }
        assert.ok(ids(route).includes("ads") && ids(route).includes("animations"));
    }
});

test("the chosen ad removal method controls setup and never silently switches to a purchase", () => {
    const desktop = plan(["ads"], "hd10-2023", "8.3.3.8", "tool");
    assert.deepEqual(ids(desktop), ["computer", "usb", "connect", "firmware-order", "ads-desktop", "finish"]);
    assert.match(words(desktop.find(s => s.id === "ads-desktop")), /8\.3\.3\.8/);
    assert.ok(!ids(plan(["ads", "play"])).includes("ads-desktop"));
    for (const profile of [["unknown", ""], ["hd10-2017", "5.3.7.3"]]) {
        const route = plan(["ads"], ...profile, "tool");
        assert.deepEqual(ids(route), ["eligibility"]);
        assert.ok(route[0].links.some(l => l.href === "ads.html#amazon"));
    }
});

test("older compatible models receive their installed Android requirements and DNS availability", () => {
    for (const [version, api] of [["6.3.1.5", 25], ["7.3.3.1", 28]]) {
        const route = plan(["play", "dns"], "hd8-2018", version);
        const files = route.find(s => s.id === "play-files");
        assert.match(words(files), new RegExp("API " + api));
        assert.ok(!files.links.some(l => l.href === "google-play.html#choose-files"));
        assert.ok(ids(route).includes(api === 25 ? "dns-limit" : "dns"));
    }
    assert.ok(!ids(plan(["dns"], "hd8-2018", "6.3.1.5")).includes("computer"));
});

test("restrictions use numeric build thresholds and do not predict Play eligibility", () => {
    for (const [model, version, restricted] of [["hd10-2023", "8.3.3.7", false], ["hd10-2023", "8.3.3.10", true],
        ["hd10-2021", "7.3.2.1", false], ["hd10-2021", "7.3.2.2", true]]) {
        const route = plan(["updates", "play"], model, version);
        const update = route.find(s => s.id === "updates");
        assert.equal(words(update).includes("v46 flags"), restricted);
        assert.ok(ids(route).includes("play"));
    }
});

test("abbreviated builds request the full firmware before interpreting restrictions", () => {
    const updates = plan(["updates"], "hd10-2023", "8.3").find(s => s.id === "updates");
    assert.match(words(updates), /full build/);
    assert.ok(!words(updates).includes("v46 flags"));
});

test("HD 10 firmware advice uses the entered version and precedes app and updater changes", () => {
    for (const [version, message] of [
        ["8.3.3.6", /Edit choices.*select Update to Fire OS 8\.3\.3\.7/i],
        ["8.3.3.7", /skip the firmware installation/i],
        ["8.3.3.8", /downgrade/i],
        ["8.3.3.10", /downgrade/i],
        ["8.3", /full version.*Edit choices/i],
    ]) {
        const route = plan(["ads", "play", "debloat", "updates", "backup"], "hd10-2023", version, "tool");
        const order = route.find(s => s.id === "firmware-order");
        assert.match(words(order), message);
        assert.ok(order.links.some(l => l.href === "hd10-8337.html#setup-order"));
        const steps = ids(route);
        const sequence = ["backup", "firmware-order", "updates", "play", "debloat", "ads-desktop", "finish"];
        assert.deepEqual(steps.filter(id => sequence.includes(id)), sequence);
        assert.doesNotMatch(route.find(s => s.id === "play").steps.join(" "), /try signing in/i);
        assert.match(words(route.at(-1)), /sign in/i);
    }
});

test("firmware advice reaches HD 10 app goals even without selecting updates", () => {
    for (const goal of ["play", "debloat", "ads", "updates"]) {
        const order = plan([goal], "hd10-2023", "8.3.3.6", "tool").find(s => s.id === "firmware-order");
        assert.match(words(order), /before.*Wi-Fi/i);
    }
    assert.ok(!ids(plan(["backup"])).includes("firmware-order"));
    assert.ok(!ids(plan(["ads"])).includes("firmware-order"));
    for (const [model, version] of [["hd10-2021", "7.3.3.1"], ["max11-2023", "8.3.3.6"], ["unknown", "8.3.3.7"]]) {
        assert.ok(!ids(plan(["play", "updates"], model, version)).includes("firmware-order"));
    }
});

const localUpdateIds = ["fw8337-prepare", "fw8337-package", "fw8337-install", "fw8337-confirm"];

test("the optional stock update is available only on the exact model and a known earlier Fire OS 8 build", () => {
    assert.ok(goals.some(goal => goal.id === "firmware-8337"));
    for (const [model, version, status] of [
        ["hd10-2023", "8.3.2.10", "available"], ["hd10-2023", "8.3.3.6", "available"],
        ["hd10-2023", "8.3.3.7", "installed"], ["hd10-2023", "8.3.3.10", "newer"],
        ["hd10-2023", "8.4.0.0", "newer"], ["hd10-2023", "8.3.3", "unknown"],
        ["hd10-2023", "", "unknown"], ["hd10-2023", "8.3.3.6rc1", "unknown"],
        ["hd10-2023", "7.3.2.1", "other"], ["hd10-2021", "8.3.3.6", "other"],
        ["hd8-2024", "8.3.3.6", "other"], ["unknown", "8.3.3.6", "other"],
    ]) {
        assert.equal(firmwareUpdateStatus(model, version), status);
        const route = plan(["firmware-8337"], model, version);
        assert.deepEqual(ids(route), status === "available" ? localUpdateIds : []);
        if (status !== "available") {
            assert.deepEqual(plan(["firmware-8337", "play"], model, version), plan(["play"], model, version));
        }
    }
});

test("standalone stock update includes the handbook package, checksum, local installation and post-restart check", () => {
    const route = plan(["firmware-8337"], "hd10-2023", "8.3.3.6");
    assert.deepEqual(ids(route), localUpdateIds);
    const [prepare, file, install, confirm] = route;
    assert.match(words(prepare), /KFTUWI/);
    assert.match(words(prepare), /back up/i);
    assert.match(words(prepare), /queued|pending/i);
    const guide = fs.readFileSync(path.join(__dirname, "../content/hd10-8337.html"), "utf8");
    const download = guide.match(/href="(https:\/\/fireos-tablet-src\.[^"]+\.bin)"/)[1];
    const digest = guide.replaceAll("<wbr>", "").match(/<code>([a-f0-9]{64})<\/code>/)[1];
    assert.ok(file.links.some(l => l.href === download));
    assert.ok(words(file).includes(digest));
    assert.match(words(install), /internal storage/i);
    assert.match(words(install), /System Updates → Update/);
    assert.match(words(confirm), /8\.3\.3\.7/);
    assert.match(words(confirm), /Edit choices/);
});

test("opting in puts all stock update steps first and resumes other goals on the confirmed firmware", () => {
    const goals = ["play", "backup", "debloat", "ads", "updates"];
    const route = plan([...goals, "firmware-8337"], "hd10-2023", "8.3.3.6", "tool");
    const steps = ids(route);
    assert.deepEqual(steps.slice(0, localUpdateIds.length), localUpdateIds);
    assert.equal(steps[localUpdateIds.length], "computer");
    assert.ok(!steps.includes("firmware-order"));
    assert.match(words(route.find(s => s.id === "connect")), /Fire OS 8\.3\.3\.7/);
    const ordered = ["backup", "updates", "play", "debloat", "ads-desktop", "finish"];
    assert.deepEqual(steps.filter(id => ordered.includes(id)), ordered);
    assert.match(words(route.find(s => s.id === "play")), /offline/i);
    assert.match(words(route.at(-1)), /sign in/i);
    assert.deepEqual(ids(plan(["firmware-8337", "animations"], "hd10-2023", "8.3.3.6")), [...localUpdateIds, "animations"]);
    const skip = plan(goals, "hd10-2023", "8.3.3.6", "tool");
    assert.ok(!ids(skip).some(id => localUpdateIds.includes(id)));
    assert.match(words(skip.find(s => s.id === "connect")), /Fire OS 8\.3\.3\.6/);
});

test("Install other APKs offers the official F-Droid client and its desktop instructions", () => {
    const sideload = plan(["sideload"]).find(section => section.id === "sideload");
    assert.match(words(sideload), /org\.fdroid\.fdroid/);
    const handbook = fs.readFileSync(path.join(__dirname, "../content/apps.html"), "utf8");
    assert.ok(sideload.links.some(link => link.href === "apps.html#fdroid"));
    const download = "https://f-droid.org/F-Droid.apk";
    assert.ok(sideload.links.some(link => link.href === download));
    assert.ok(handbook.includes('href="' + download + '"'));
    assert.match(handbook, /f-droid\.org\/[^"]*Release_Channels_and_Signing_Keys\//);
});

test("backup precedes changes and SDK verification is shared only by install goals", () => {
    assert.deepEqual(ids(plan(["debloat", "backup"])), ids(plan(["backup", "debloat", "backup"])));
    const route = ids(plan(["debloat", "backup"]));
    assert.ok(route.indexOf("backup") < route.indexOf("debloat"));
    assert.ok(!route.includes("apk-tools"));
    const withAnimations = ids(plan(["animations", "backup"]));
    assert.ok(withAnimations.indexOf("backup") < withAnimations.indexOf("animations"));
    const all = ids(plan(goals.map(g => g.id)));
    assert.ok(all.indexOf("backup") < all.indexOf("updates"));
    assert.ok(all.indexOf("updates") < all.indexOf("play"));
    assert.ok(all.indexOf("updates") < all.indexOf("ads"));
    assert.equal(ids(plan(["sideload", "play"])).filter(id => id === "apk-tools").length, 1);
});

test("every offered choice produces bounded readable sections and valid handbook links", () => {
    const content = path.join(__dirname, "../content");
    assert.equal(new Set(models.map(m => m.id)).size, models.length);
    assert.equal(new Set(goals.map(g => g.id)).size, goals.length);
    for (const model of models) for (const version of ["", "5.3.7.3", "6.3.1.5", "7.3.3.1", "8.3.3.6", "8.3.3.8"]) {
        const route = plan(goals.map(g => g.id), model.id, version);
        const tool = plan(["ads"], model.id, version, "tool");
        assert.equal(new Set(ids(route)).size, route.length);
        assert.equal(route.at(-1).id === "finish", ids(route).includes("usb"));
        for (const section of [...route, ...tool]) {
            assert.ok(section.title && section.intro && section.check);
            assert.ok(section.steps.length >= 2 && section.steps.length <= 4);
            for (const {label, href} of section.links) {
                assert.ok(label);
                if (href.startsWith("https://")) continue;
                const [page, anchor] = href.split("#");
                const html = fs.readFileSync(path.join(content, page), "utf8");
                if (anchor) assert.ok(html.includes('id="' + anchor + '"'), href);
            }
        }
    }
});
