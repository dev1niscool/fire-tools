import assert from "node:assert/strict";
import test from "node:test";
import { connectUsb, shellArgs, readHash, runShell } from "../adapter.js";

test("arguments stay separate on the device shell", () => {
    assert.equal(shellArgs(["settings", "read only", "owner's", ""]), "'settings' 'read only' 'owner'\\''s' ''");
    for (const args of [[], ["ls", "bad\nname"], [null], ["x".repeat(7000)]])
        assert.throws(() => shellArgs(args));
});

function bytes(parts) {
    return new ReadableStream({
        start(controller) {
            for (const part of parts) controller.enqueue(Uint8Array.from(part));
            controller.close();
        }
    });
}

test("installed-byte hashing honors size and exact received bytes", async () => {
    const actual = await readHash(bytes([[97], [98, 99]]), 3);
    assert.deepEqual(actual, {
        size: 3, sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    });
    await assert.rejects(readHash(bytes([[1, 2, 3]]), 2), /size/);
});

function processFor(stdout, stderr, code) {
    const encode = value => bytes([new TextEncoder().encode(value)]);
    return {stdout: encode(stdout), stderr: encode(stderr), stdin: new WritableStream(), exited: Promise.resolve(code), kill: async () => {}};
}

test("shell requires stdout and the actual exit status", async () => {
    const make = proc => ({subprocess: {shellProtocol: {spawn: async () => proc}}});
    assert.equal(await runShell(make(processFor("hello\n", "", 0)), ["test"]), "hello");
    await assert.rejects(runShell(make(processFor("", "permission denied", 1)), ["test"]), /permission denied/);
    await assert.rejects(runShell(make(processFor("x".repeat(1024 * 1024 + 1), "", 0)), ["test"]), /output/);
});

test("canceling an outstanding chooser opens no USB session", async () => {
    let select, requested = 0;
    Object.defineProperty(navigator, "usb", {
        configurable: true,
        value: { requestDevice: () => {
            requested++;
            return new Promise(resolve => { select = resolve; });
        } }
    });
    try {
        const ctrl = new AbortController();
        const pending = connectUsb(ctrl.signal);
        assert.equal(requested, 1);
        ctrl.abort(new Error("User canceled"));
        await assert.rejects(pending, /User canceled/);
        select(undefined);
        await assert.rejects(connectUsb(ctrl.signal), /User canceled/);
        assert.equal(requested, 1);
    } finally {
        delete navigator.usb;
    }
});

test("streamed install input preserves exact file bytes", async () => {
    const input = Uint8Array.of(255, 0, 1, 19, 42);
    const received = [];
    let command;
    const proc = processFor("Success\n", "", 0);
    proc.stdin = new WritableStream({write: chunk => received.push(...chunk)});
    const adb = {subprocess: {shellProtocol: {spawn: async args => {
        command = args; return proc;
    }}}};
    assert.equal(await runShell(adb, ["cmd", "package", "install", "-r", "--user", "0", "-S", "5"], new Blob([input])), "Success");
    assert.deepEqual(command, ["'cmd' 'package' 'install' '-r' '--user' '0' '-S' '5'"]);
    assert.deepEqual(received, Array.from(input));
});

test("reviewed in-memory APK bytes stream in bounded chunks in exact order", async () => {
    const original = Uint8Array.from({length: 155000}, (_, i) => i % 251);
    const parts = [];
    const proc = processFor("Success\n", "", 0);
    proc.stdin = new WritableStream({write: bytes => parts.push(bytes)});
    const adb = {subprocess: {shellProtocol: {spawn: async () => proc}}};
    assert.equal(await runShell(adb, ["cmd", "package", "install"], original), "Success");
    assert.ok(parts.every(part => part.length <= 65536));
    assert.deepEqual(Buffer.concat(parts), Buffer.from(original));
});
