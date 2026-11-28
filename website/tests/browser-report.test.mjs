import test from "node:test";
import assert from "node:assert/strict";
import { createInventoryExport, previewSharedFile, readInstalledPackages, readReport } from "../assets/browser-report.mjs";

const device = {
  manufacturer: "Amazon", model: "KFTUWI", fireOS: "8.3.3.8", sdk: 30,
  abis: ["arm64-v8a", "armeabi-v7a"], user: 0, serial: "PRIVATE_TABLET_SERIAL",
};
const replies = {
  "dumpsys battery": "Current Battery Service state:\n  level: 72\n  scale: 80\n  serial: private battery serial\n",
  "df -k /data": "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-6 16777216 4194304 12582912 25% /data\n",
  "pm list packages --user 0": "package:com.amazon.kindle\r\npackage:android\r\n",
  "pm list packages --user 0 -d": "package:com.amazon.kindle\n",
  "settings --user 0 get global window_animation_scale": "0.5\n",
  "settings --user 0 get global transition_animation_scale": "null\n",
  "settings --user 0 get global animator_duration_scale": "1.0\n",
  "settings --user 0 get global private_dns_mode": "hostname\n",
};

function tablet(overrides = {}, profile = device) {
  return {
    device: profile, commands: [], identities: 0,
    async assertIdentity() { this.identities++; },
    async shell(args) {
      const command = args.join(" ");
      this.commands.push(command);
      const data = { ...replies, ...overrides };
      assert.ok(Object.hasOwn(data, command), command);
      if (data[command] instanceof Error) throw data[command];
      return data[command];
    },
  };
}

test("diagnostics show model, owner profile, battery and available storage without identifiers", async () => {
  const session = tablet();
  const text = await readReport(session);
  for (const detail of ["KFTUWI", "8.3.3.8", "30", "arm64-v8a", "90%", "12 GiB", "16 GiB"]) {
    assert.ok(text.includes(detail), detail);
  }
  assert.doesNotMatch(text, /private|dm-6/i);
  assert.deepEqual(session.commands, ["dumpsys battery", "df -k /data"]);
  assert.equal(session.identities, 2);
});

test("inventory export includes only selected settings and installed owner packages", async () => {
  const session = tablet();
  const text = await createInventoryExport(session);
  const result = JSON.parse(text);
  assert.equal(result.format, "fire-tools.browser-inventory.v1");
  assert.deepEqual(result.packages, [
    {package: "android", state: "enabled"},
    {package: "com.amazon.kindle", state: "disabled"},
  ]);
  assert.deepEqual(result.settings, {
    window_animation_scale: "0.5", transition_animation_scale: null,
    animator_duration_scale: "1.0", private_dns_mode: "hostname",
  });
  assert.doesNotMatch(text, /private_tablet_serial|private battery serial|dm-6/i);
  assert.equal(new Set(session.commands).size, Object.keys(replies).length);
  assert.equal(session.identities, 2);
});

test("earlier Android omits Private DNS and reports unrecognized optional metrics as unavailable", async () => {
  const session = tablet({"df -k /data": "Access denied", "dumpsys battery": "  scale: 0\n  level: 88"}, {...device, sdk: 25});
  const result = JSON.parse(await createInventoryExport(session));
  assert.equal(result.diagnostics.batteryPercent, null);
  assert.equal(result.diagnostics.dataStorage, null);
  assert.ok(!Object.hasOwn(result.settings, "private_dns_mode"));
  assert.ok(!session.commands.includes("settings --user 0 get global private_dns_mode"));
});

test("an incomplete or inconsistent package read cannot produce a misleading report", async () => {
  for (const rows of ["package:com.unknown\n", "Android error!\n"]) {
    await assert.rejects(() => readInstalledPackages(tablet({"pm list packages --user 0 -d": rows})), /package/i);
  }
  await assert.rejects(() => readInstalledPackages(tablet({"pm list packages --user 0": ""})), /package/i);
});

test("export blocks other profiles and rejects a device change during collection", async () => {
  const other = tablet({}, {...device, user: 10});
  await assert.rejects(() => createInventoryExport(other), /owner|adult/i);
  assert.equal(other.commands.length, 0);
  const changed = tablet();
  changed.assertIdentity = async function () {
    if (++this.identities === 2) throw Error("Tablet changed");
  };
  await assert.rejects(() => createInventoryExport(changed), /Tablet changed/);
});

test("refusals and unexpected setting values cannot be exported as valid settings", async () => {
  for (const data of [
    {"settings --user 0 get global animator_duration_scale": "Permission denied"},
    {"settings --user 0 get global private_dns_mode": "private-network-name"},
  ]) {
    await assert.rejects(() => createInventoryExport(tablet(data)), /setting/i);
  }
});

test("unavailable optional metrics do not block the owner's settings export", async () => {
  const session = tablet({
    "dumpsys battery": new Error("Battery service refused"),
    "settings --user 0 get global window_animation_scale": "5.0E-1",
    "pm list packages --user 0": "package:android\npackage:com.android._overlay",
    "pm list packages --user 0 -d": "",
  });
  const result = JSON.parse(await createInventoryExport(session));
  assert.equal(result.diagnostics.batteryPercent, null);
  assert.equal(result.diagnostics.dataStorage.totalKiB, 16777216);
  assert.equal(result.settings.window_animation_scale, "5.0E-1");
  assert.equal(result.packages.length, 2);
});

test("download preview retains the reviewed filename, digest and exact bytes", async () => {
  const source = new TextEncoder().encode("abc");
  const session = {device, async readSharedFile(path, limit) {
    assert.equal(path, "/storage/emulated/0/DCIM/Camera/picture.jpg");
    assert.equal(limit, 32 * 1024 ** 2);
    return source;
  }};
  const staged = await previewSharedFile(session, "DCIM", "Camera/picture.jpg");
  source.fill(255);
  assert.equal(staged.filename, "picture.jpg");
  assert.equal(staged.size, 3);
  assert.equal(staged.sha256, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  assert.equal(staged.blob.type, "application/octet-stream");
  assert.equal(await staged.blob.text(), "abc");
});

test("preview rejects a parent, absolute or hidden-direction path and another Android profile", async () => {
  const owner = {device, readSharedFile: assert.fail};
  const child = {device: {...device, user: 10}, readSharedFile: assert.fail};
  for (const relative of ["../private", "/private", "photo/./other", "im\u202Egpj", "a\\b"]) {
    await assert.rejects(previewSharedFile(owner, "Pictures", relative), /file path/);
  }
  await assert.rejects(previewSharedFile(owner, "Documents", "file"), /file path/);
  await assert.rejects(previewSharedFile(child, "Download", "file"), /adult|owner/);
});

test("an explicitly empty Private DNS mode remains distinct from an absent setting", async () => {
  for (const [raw, expected] of [["\n", ""], ["null\n", null]]) {
    const report = JSON.parse(await createInventoryExport(tablet({"settings --user 0 get global private_dns_mode": raw})));
    assert.equal(report.settings.private_dns_mode, expected);
  }
});
