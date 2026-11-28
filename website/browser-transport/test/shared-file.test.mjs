import assert from "node:assert/strict";
import test from "node:test";
import {mkdtemp, mkdir, writeFile, symlink, link, rm} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {spawn} from "node:child_process";
import {Readable} from "node:stream";
import {readSharedFile} from "../shared-file.js";

const root = "/storage/emulated/0/Download";
const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";

async function shellTablet(t, filename, bytes) {
    const dir = await mkdtemp(join(tmpdir(), "fire-shared-"));
    t.after(() => rm(dir, {recursive: true, force: true}));
    const allowed = join(dir, "Download");
    await mkdir(allowed);
    await writeFile(join(allowed, filename), bytes);
    const env = {...process.env};
    return {
        dir, allowed, env,
        adb: {subprocess: {shellProtocol: {
            isSupported: true,
            async spawn(argv) {
                // Keep the actual device script and quoting. Map only the
                // virtual storage prefix to the test's temporary directory.
                const cmd = argv.join(" ").replace(quote(root + "/").slice(0, -1), quote(allowed + "/").slice(0, -1));
                const child = spawn("/bin/sh", ["-c", cmd], {env});
                return {
                    stdout: Readable.toWeb(child.stdout), stderr: Readable.toWeb(child.stderr),
                    exited: new Promise(resolve => child.once("exit", resolve)),
                    kill: () => child.kill(),
                };
            }
        }}},
    };
}

test("shared file transfer verifies real binary bytes through an opened file", {skip: process.platform !== "linux"}, async t => {
    const data = Uint8Array.of(0, 255, 9, 3, 10, 13);
    const file = "Jane's #photo.jpg";
    const {adb} = await shellTablet(t, file, data);
    assert.deepEqual(await readSharedFile(adb, "/sdcard/Download/" + file, data.length), data);
});

test("empty, too-large, symlinked and missing files are distinguished", {skip: process.platform !== "linux"}, async t => {
    const {adb, dir, allowed} = await shellTablet(t, "empty", "");
    assert.equal((await readSharedFile(adb, root + "/empty", 10)).byteLength, 0);
    await writeFile(join(allowed, "large"), "abcdef");
    await assert.rejects(readSharedFile(adb, root + "/large", 2), /size|limit|large/i);
    await writeFile(join(dir, "outside"), "private");
    await symlink(join(dir, "outside"), join(allowed, "alias"));
    await symlink(dir, join(allowed, "linked-dir"));
    await link(join(dir, "outside"), join(allowed, "hard-link"));
    for (const name of ["alias", "linked-dir/outside", "hard-link", "missing"]) {
        await assert.rejects(readSharedFile(adb, root + "/" + name, 10), /ordinary|changed|read|link|find/i);
    }
});

test("same-size content changes during transfer cannot be offered for download", {skip: process.platform !== "linux"}, async t => {
    const {adb, dir, allowed, env} = await shellTablet(t, "note.txt", "first version");
    // An ordinary writer edits the open file after its initial read and before
    // the tablet computes the independent digest, keeping its length constant.
    const bin = join(dir, "test-bin");
    await mkdir(bin);
    await writeFile(join(bin, "head"), [
        "#!/bin/sh",
        'PATH="$ORIGINAL_TEST_PATH" head "$@" || exit 1',
        'printf "%s" "other version" > "$FILE_BEING_EDITED"',
    ].join("\n") + "\n", {mode: 0o755});
    env.ORIGINAL_TEST_PATH = env.PATH;
    env.PATH = bin + ":" + env.PATH;
    env.FILE_BEING_EDITED = join(allowed, "note.txt");
    await assert.rejects(readSharedFile(adb, root + "/note.txt", 32), /checksum|stable/);
});

test("only bounded owner shared-storage file paths reach the shell", async () => {
    const adb = {subprocess:{shellProtocol:{isSupported:true, spawn:assert.fail}}};
    for (const path of ["/data/secret", "/sdcard/Download/../file", "/sdcard/Download/item/./a", "/sdcard/Download//a",
        "/sdcard/Download/a\nb", "/storage/emulated/10/Pictures/x", "/sdcard/Download", "/storage/emulated/0/Downloads/x"]) {
        await assert.rejects(readSharedFile(adb, path, 20), /path|file|folder/i);
    }
    for (const limit of [Infinity, 0, -1, 0.5, 33 * 1024 ** 2]) {
        await assert.rejects(readSharedFile(adb, root + "/a", limit), /limit/i);
    }
});

function stream(bytes) {
    return new ReadableStream({start(ctrl) { ctrl.enqueue(bytes); ctrl.close(); }});
}
test("mismatched digest, size, uncapped stdout, and missing receipt never return a file", async () => {
    const hash = "f".repeat(64);
    let killed = 0;
    for (const [data, receipt] of [
        [[0], "FIRE-FILE 1 " + hash], [[0, 1], "FIRE-FILE 1 " + hash],
        [[0, 1, 2], ""], [[0], ""], [[0], "FIRE-FILE 1 " + hash + "\nextra"]
    ]) {
        const adb = {subprocess:{shellProtocol:{isSupported:true, async spawn() {
            return {stdout:stream(Uint8Array.from(data)), stderr:stream(new TextEncoder().encode(receipt)),
                exited:Promise.resolve(0), kill() { killed++; }};
        }}}};
        await assert.rejects(readSharedFile(adb, root + "/a", 2), /verify|limit|size|checksum|read/i);
    }
    assert.ok(killed);
});
