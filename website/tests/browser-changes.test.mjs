import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {test} from "node:test";
import {changeActions, isManagedChangeWrite, previewChange} from "../assets/browser-changes.mjs";

const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

class Memory {
  values = new Map();
  getItem(k) { return this.values.get(k) ?? null; }
  setItem(k, v) { this.values.set(k, v); }
  removeItem(k) { this.values.delete(k); }
}

const device = {serial:"FIRE123", identityKey:"01".repeat(32), model:"KFTUWI", sdk:30, manufacturer:"Amazon", user:0};
const adb = (packages = {}) => ({
  async assertIdentity() {}, pkgs: new Map(Object.entries(packages)), settings: new Map(), writes: [], async shell(args) {
    if (args[0] === "settings") {
      const [, flag, user, verb, table, key, value] = args;
      assert.deepEqual([flag, user, table], ["--user", "0", "global"]);
      if (verb === "list") return ["adb_enabled=1", ...[...this.settings].map(([k,v]) => k+"="+v)].join("\n");
      assert.ok(verb === "put" || verb === "delete");
      this.writes.push(args);
      if (this.reject === key) throw Error("Fire OS denied this write");
      if (verb === "put") this.settings.set(key, value);
      else this.settings.delete(key);
      return "";
    }
    if (args[0] === "pm" && args[1] === "list") {
      assert.deepEqual(args.slice(1, 5), ["list","packages","--user","0"]);
      const filter = args.slice(5).find(x => !x.startsWith("-"));
      return [...this.pkgs].filter(([k,v]) => (!filter || k.includes(filter)) && (!args.includes("-d") || v.disabled) &&
        (!args.includes("-s") || v.system)).map(([k])=>"package:"+k).join("\n");
    }
    if (args[0] === "dumpsys") {
      const p = args[2], mode = this.pkgs.get(p).mode;
      return "Packages:\n  Package ["+p+"] (012ab):\n    User 0: installed=true enabled="+mode+"\nHidden system packages:\n  Package ["+p+"] (feed):\n    User 0: installed=true enabled=4";
    }
    const [cmd,verb,flag,user,key] = args;
    assert.deepEqual([cmd,flag,user], ["pm","--user","0"]);
    this.writes.push(args);
    if (this.reject === key) throw Error("Fire OS denied this write");
    const pkg = this.pkgs.get(key);
    pkg.mode = ["default-state","enable","disable","disable-user","disable-until-used"].indexOf(verb);
    pkg.disabled = pkg.mode >= 2;
    return "";
  }
});
function fixture() {
  const storage = new Memory();
  const preview = (s,id,d=device) => previewChange(s,d,id,storage);
  return {storage,preview};
}
const noop = () => {};

test("previews and restores the real Standard and Complete preset membership with exact Android owner modes", async () => {
  const catalog = JSON.parse(execFileSync(python, ["-c","from open_fire_toolkit.package_catalog import DEBLOAT_PROFILES,is_protected;import json;print(json.dumps({k:[p for p in DEBLOAT_PROFILES[k] if not is_protected(p)] for k in ('standard','complete')}))"], {cwd:new URL("../../",import.meta.url)}));
  for (const profile of ["standard","complete"]) {
    const {preview,storage} = fixture();
    const original = Object.fromEntries([...catalog.complete,"com.amazon.kindle.otter.oobe"].map((name,i)=>[name,{mode:i%2,disabled:false,system:true}]));
    const s = adb(structuredClone(original));
    const plan = await preview(s,"debloat-"+profile);
    assert.equal(s.writes.length,0);
    if (profile === "complete") assert.match(plan.details.join("\n"),/Device Setup.*protected/i);
    await plan.apply(noop);
    assert.deepEqual(s.writes.map(a=>a.at(-1)).sort(),catalog[profile].sort());
    assert.ok(s.writes.every(a => a[1] === "disable-user"));
    await (await preview(s,"debloat-undo")).apply(noop);
    assert.deepEqual(Object.fromEntries(s.pkgs),original);
    assert.equal(storage.values.size,0);
  }
});

test("partial batch failure retains originals and restores only attempted changes", async () => {
  const {preview} = fixture(), first="com.amazon.ags.app", second="com.amazon.geo.client.maps";
  const s=adb({[first]:{mode:0,disabled:false,system:true},[second]:{mode:1,disabled:false,system:true}});
  s.reject=second;
  await assert.rejects((await preview(s,"debloat-standard")).apply(noop),/denied/);
  s.reject=null;
  await (await preview(s,"debloat-undo")).apply(noop);
  assert.deepEqual(s.writes.map(a=>a[1]),["disable-user","disable-user","default-state"]);
});

test("ads changes require writable recovery, preserve absent and reject stale previews", async () => {
  const {preview,storage}=fixture(), s=adb();
  const plan=await preview(s,"ads-disable");
  s.settings.set("LOCKSCREEN_AD_ENABLED","1");
  await assert.rejects(plan.apply(noop),/changed/i);
  s.settings.clear();
  const blocked=await preview(s,"ads-disable");
  storage.setItem=()=>{throw Error("quota");};
  await assert.rejects(blocked.apply(noop),/recovery|undo/i);
  assert.equal(s.writes.length,0);
  delete storage.setItem;
  await (await preview(s,"ads-disable")).apply(noop);
  assert.equal(s.settings.get("LOCKSCREEN_AD_ENABLED"),"0");
  assert.equal((await preview(s,"ads-undo",{...device,serial:"another",identityKey:"02".repeat(32)})).apply,null);
  await (await preview(s,"ads-undo")).apply(noop);
  assert.equal(s.settings.has("LOCKSCREEN_AD_ENABLED"),false);
});

test("animation and DNS choices retain the first originals and delete only genuinely missing settings", async () => {
  const {preview}=fixture(),s=adb();
  s.settings.set("window_animation_scale","1.25");
  await (await preview(s,"animations-fast")).apply(noop);
  await (await preview(s,"animations-standard")).apply(noop);
  await (await preview(s,"animations-undo")).apply(noop);
  assert.deepEqual([...s.settings],[["window_animation_scale","1.25"]]);
  s.settings.set("private_dns_mode","off");
  await (await preview(s,"dns-quad9")).apply(noop);
  assert.deepEqual([s.settings.get("private_dns_specifier"),s.settings.get("private_dns_mode")],["dns.quad9.net","hostname"]);
  await (await preview(s,"dns-auto")).apply(noop);
  await (await preview(s,"dns-undo")).apply(noop);
  assert.equal(s.settings.get("private_dns_mode"),"off");
  assert.ok(!s.settings.has("private_dns_specifier"));
  await assert.rejects(preview(s,"dns-quad9",{...device,sdk:25}),/Android 9|SDK 28/);
});

test("updater status has no side effects, skips non-system and verifies success", async () => {
  const {preview}=fixture(),a="com.amazon.device.software.ota", b=a+".override";
  const s=adb({[a]:{mode:0,disabled:false,system:true},[b]:{mode:0,disabled:false,system:false}});
  const report=await preview(s,"updates-status");
  assert.equal(report.apply,null);
  assert.match(report.details.join("\n"),/system/i);
  await (await preview(s,"updates-disable")).apply(noop);
  assert.deepEqual(s.writes.map(a=>a.at(-1)),[a]);
  await (await preview(s,"updates-undo")).apply(noop);
  assert.equal(s.pkgs.get(a).mode,0);
});

test("unrecognized commands, malformed journals and shell error output cannot produce a write", async () => {
  const {preview,storage}=fixture(), s=adb();
  await assert.rejects(preview(s,"some-command"));
  await (await preview(s,"ads-disable")).apply(noop);
  const k=[...storage.values.keys()][0];
  storage.setItem(k,JSON.stringify({entries:[{key:"unreviewed",before:"1"}]}));
  await assert.rejects(preview(s,"ads-undo"),/recovery|undo/i);
  assert.equal(s.writes.length,1);
  const bad={shell:async()=> "Permission denial: unknown command"};
  await assert.rejects(preview(bad,"debloat-standard"),/response|deni/i);
  assert.ok(changeActions.length>=10);
});

test("DNS mode remains untouched if another process replaces the resolver after hostname verification", async () => {
  const {preview}=fixture(),s=adb();
  const plan=await preview(s,"dns-quad9");
  await assert.rejects(plan.apply(note=>{
    if (note.startsWith("Verified private_dns_specifier")) s.settings.set("private_dns_specifier","other.example");
  }),/changed|verify/i);
  assert.equal(s.settings.has("private_dns_mode"),false);
  await (await preview(s,"dns-undo")).apply(noop);
  assert.equal(s.settings.has("private_dns_specifier"),false);
});

test("a claimed package change without matching readback fails and retains recovery", async () => {
  const s=adb({"com.amazon.kindle":{mode:1,disabled:false,system:true}}), {preview,storage}=fixture();
  const real=s.shell.bind(s);
  s.shell=args=>args[1]==="disable-user" ? "success" : real(args);
  await assert.rejects((await preview(s,"debloat-standard")).apply(noop),/verify/i);
  assert.equal(storage.values.size,1);
  await (await preview(s,"debloat-undo")).apply(noop);
  assert.equal(storage.values.size,0);
  assert.equal(s.writes.length,0);
});

test("the browser refuses ambiguous package rows and secondary-profile writes", async () => {
  const {preview}=fixture(),s=adb({"com.amazon.kindle":{mode:1,disabled:false,system:true}});
  const real=s.shell.bind(s);
  s.shell=args=>args[0]==="dumpsys" ? "User 0: installed=true enabled=1\nUser 0: installed=true enabled=0" : real(args);
  await assert.rejects(preview(s,"debloat-standard"),/exact.*state/i);
  await assert.rejects(preview(s,"ads-disable",{...device,user:10}),/User 0/i);
  await assert.rejects(preview(s,"ads-disable",{...device,sdk:22}),/SDK 23/i);
  assert.equal(s.writes.length,0);
});

test("a stable hardware identity supports recovery even if the USB descriptor serial is missing or changes", async () => {
  const {preview}=fixture(),s=adb();
  const stable={...device,identityKey:"ab".repeat(32),serial:""};
  await (await preview(s,"ads-disable",stable)).apply(noop);
  await (await preview(s,"ads-undo",{...stable,serial:"USB_ALIAS"})).apply(noop);
  assert.equal(s.settings.has("LOCKSCREEN_AD_ENABLED"),false);
  await assert.rejects(preview(s,"ads-disable",{...device,identityKey:""}),/identity|identifier/i);
});

test("all six browser DNS presets use the desktop hostnames and preserve the original mode and host", async () => {
  const presets=JSON.parse(execFileSync(python,["-c","from open_fire_toolkit.extra_workflows import DNS_PRESETS;import json;print(json.dumps({k:v[0] for k,v in DNS_PRESETS.items()}))"],{cwd:new URL("../../",import.meta.url)}));
  const {preview}=fixture(),s=adb();
  s.settings.set("private_dns_mode","hostname");
  s.settings.set("private_dns_specifier","original.example");
  for (const [id,host] of Object.entries(presets)) {
    const p=await preview(s,"dns-"+id);
    assert.ok(p.details.some(text=>text.includes(host)));
    assert.match(p.warnings.join(" "),/domain names/);
    await p.apply(noop);
    assert.equal(s.settings.get("private_dns_specifier"),host);
    assert.equal(s.settings.get("private_dns_mode"),"hostname");
  }
  await (await preview(s,"dns-undo")).apply(noop);
  assert.equal(s.settings.get("private_dns_specifier"),"original.example");
  assert.equal(s.settings.get("private_dns_mode"),"hostname");
});

test("Special Offers controls require a system package and independently preserve the package and setting originals",async()=>{
  const {preview}=fixture(),key="com.amazon.kindle.kso";
  const s=adb({[key]:{mode:0,disabled:false,system:false}});
  assert.equal((await preview(s,"offers-disable")).apply,null);
  s.pkgs.get(key).system=true;
  await (await preview(s,"ads-disable")).apply(noop);
  const plan=await preview(s,"offers-disable");
  assert.match(plan.warnings.join(" "),/visibility|lock screen/i);
  await plan.apply(noop);
  assert.equal(s.pkgs.get(key).mode,3);
  await (await preview(s,"offers-undo")).apply(noop);
  assert.equal(s.pkgs.get(key).mode,0);
  assert.equal(s.settings.get("LOCKSCREEN_AD_ENABLED"),"0");
  await (await preview(s,"ads-undo")).apply(noop);
  assert.equal(s.settings.has("LOCKSCREEN_AD_ENABLED"),false);
});

test("transport write policy admits only exact user-0 catalog operations and restorable values", () => {
  for (const verb of ["default-state","enable","disable","disable-user","disable-until-used"]) {
    for (const name of ["com.amazon.kindle","com.amazon.device.software.ota","com.amazon.kindle.kso"]) {
      assert.ok(isManagedChangeWrite(["pm",verb,"--user","0",name]));
    }
  }
  const setting = (verb,...tail) => ["settings","--user","0",verb,"global",...tail];
  for (const [key,value] of [["LOCKSCREEN_AD_ENABLED","1"],["window_animation_scale","0.5"],
    ["private_dns_mode","hostname"],["private_dns_specifier","example.org"],["private_dns_specifier",""]]) {
    assert.ok(isManagedChangeWrite(setting("put",key,value)));
    assert.ok(isManagedChangeWrite(setting("delete",key)));
  }
  for (const args of [null,[],["pm","disable-user","--user","0","com.amazon.kindle.otter.oobe"],
    ["pm","clear","--user","0","com.amazon.kindle"],["pm","enable","--user","1","com.amazon.kindle"],
    ["pm","enable","--user","0","com.android.providers.calendar"],["pm","enable","--user","0","com.amazon.kindle","extra"],
    ["settings","--user","0","put","secure","LOCKSCREEN_AD_ENABLED","1"],
    setting("put","private_dns_specifier","invalid/host"),setting("put","private_dns_mode","bogus"),
    setting("put","LOCKSCREEN_AD_ENABLED",null),setting("put","window_animation_scale","NaN"),
    setting("delete","unknown"),setting("delete","private_dns_mode","extra")]) {
    assert.equal(isManagedChangeWrite(args),false,JSON.stringify(args));
  }
});
