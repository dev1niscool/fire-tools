const MAX_BYTES = 32 * 1024 * 1024;

// Keep the open descriptor across validation, transfer and the second read.
// The shell sends the digest and size on stderr, separate from the file bytes.
const FILE_READER = `
file=$1
limit=$2
[ -f "$file" ] && [ ! -L "$file" ] && [ "$(readlink -f "$file")" = "$file" ] || exit 20
exec 3< "$file" || exit 20
fd=/proc/$$/fd/3
[ -f "$fd" ] && [ "$(readlink "$fd")" = "$file" ] || exit 20
[ "$(stat -L -c '%h' "$fd")" = 1 ] || exit 20
before=$(stat -L -c '%d:%i:%s:%Y:%Z' "$fd") || exit 20
size=$(stat -L -c '%s' "$fd") || exit 20
case "$size" in ''|*[!0-9]*) exit 20;; esac
[ "$size" -le "$limit" ] || exit 21
head -c "$size" <&3 || exit 22
digest=$(head -c "$size" < "$fd" | sha256sum) || exit 22
[ "$before" = "$(stat -L -c '%d:%i:%s:%Y:%Z' "$file")" ] &&
    [ "$(readlink "$fd")" = "$file" ] && [ "$(readlink -f "$file")" = "$file" ] || exit 22
printf 'FIRE-FILE %s %s\\n' "$size" "\${digest%% *}" >&2
`;

function canonicalPath(path) {
    if (typeof path !== "string" || new TextEncoder().encode(path).length > 1024 ||
        /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}\\]/u.test(path))
        throw new Error("Choose a valid shared file path.");
    const match = /^(?:\/sdcard|\/storage\/emulated\/0)\/(Download|DCIM|Pictures)\/(.+)$/u.exec(path);
    if (!match || match[2].split("/").some(part => !part || part === "." || part === ".."))
        throw new Error("Choose a file inside Download, DCIM or Pictures.");
    return "/storage/emulated/0/" + match[1] + "/" + match[2];
}

const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";

async function collect(stream, limit) {
    const reader = stream.getReader();
    const result = new Uint8Array(limit);
    let count = 0;
    try {
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            if (value.length > limit - count) throw new Error("The shared file transfer exceeded its size limit.");
            result.set(value, count);
            count += value.length;
        }
    } finally {
        reader.releaseLock();
    }
    return result.slice(0, count);
}

export async function readSharedFile(adb, path, maxBytes) {
    const file = canonicalPath(path);
    if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX_BYTES)
        throw new Error("The shared file size limit must be between 1 byte and 32 MiB.");
    const shell = adb.subprocess.shellProtocol;
    if (!shell?.isSupported) throw new Error("This tablet needs ADB shell v2 for a verified shared file download.");
    const proc = await shell.spawn(["sh", "-c", quote(FILE_READER), "fire-tools", quote(file), String(maxBytes)]);
    try {
        const [bytes, meta, code] = await Promise.all([
            collect(proc.stdout, maxBytes), collect(proc.stderr, 1024), proc.exited,
        ]);
        if (code === 21) throw new Error("This file exceeds the selected size limit (maximum 32 MiB).");
        if (code !== 0) throw new Error("Could not read a stable, ordinary file. Check the path, USB connection and tablet permissions.");
        const receipt = /^FIRE-FILE (\d+) ([\da-f]{64})\n?$/.exec(new TextDecoder().decode(meta));
        if (!receipt || Number(receipt[1]) !== bytes.length)
            throw new Error("Could not verify the file size from the tablet. Read the file again.");
        const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
        const hex = Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
        if (hex !== receipt[2]) throw new Error("The file checksum changed during transfer. Read the file again.");
        return bytes;
    } catch (error) {
        await Promise.resolve(proc.kill()).catch(() => {});
        throw error;
    }
}
