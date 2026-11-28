(() => {
  // Test-only USB device. Chrome runs the production connection and APK code.
  // The device answers the ADB handshake, shell-v2 and SYNC/RECV packets.
  const encoder = new TextEncoder(),
    decoder = new TextDecoder();
  const encode = (s) => encoder.encode(s);
  function concatBytes(...arrays) {
    const out = new Uint8Array(arrays.reduce((sum, a) => sum + a.length, 0));
    let offset = 0;
    for (const a of arrays) {
      out.set(a, offset);
      offset += a.length;
    }
    return out;
  }
  function uint32(n) {
    const bytes = new Uint8Array(4);
    new DataView(bytes.buffer).setUint32(0, n, true);
    return bytes;
  }
  function readUint32(buffer, offset = 0) {
    return new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength).getUint32(offset, true);
  }
  function commandId(s) {
    return readUint32(encode(s));
  }
  window.USBConnectionEvent = class extends Event {
    constructor(type, init) {
      super(type);
      this.device = init.device;
    }
  };
  const usb = new EventTarget();
  // Only the fixture and the Playwright harness see this state. The site sees WebUSB.
  const data = (window.mockTablet = {
    properties: {
      "ro.product.model": "KFTUWI",
      "ro.product.manufacturer": "Amazon",
      "ro.build.mktg.fireos": "8.3.3.8",
      "ro.build.version.name": "8.3.3.8",
      "ro.build.version.sdk": "30",
      "ro.build.version.release": "11",
      "ro.product.cpu.abilist": "arm64-v8a,armeabi-v7a",
      "ro.product.cpu.abi": "arm64-v8a",
      "ro.serialno": "GNEWUSBTEST123",
      "ro.boot.serialno": "GNEWUSBTEST123",
      "ro.build.fingerprint": "Amazon/test/fire:11/TEST",
      "ro.product.device": "tungsten",
    },
    selectedUser: 0,
    chooserCount: 0,
    authKeys: 0,
    requests: [],
    commands: [],
    wire: [],
    failures: [],
    installs: [],
    reads: [],
    writes: [],
    settings: {
      global: { window_animation_scale: "1", transition_animation_scale: "1", animator_duration_scale: "1" },
      secure: {},
      system: {},
    },
    packages: {
      "com.amazon.kindle": 0,
      "com.amazon.kindle.kso": 0,
      "com.amazon.device.software.ota": 0,
      "com.amazon.device.software.ota.override": 0,
      "com.android.providers.calendar": 0,
      "com.android.providers.contacts": 0,
    },
    installed: {},
    filesBySize: {},
    features: "shell_v2",
    offline: false,
  });
  const alternate = {
    alternateSetting: 0,
    interfaceClass: 255,
    interfaceSubclass: 66,
    interfaceProtocol: 1,
    endpoints: [
      { endpointNumber: 1, direction: "in", packetSize: 512, type: "bulk" },
      { endpointNumber: 1, direction: "out", packetSize: 512, type: "bulk" },
    ],
  };
  const usbInterface = { interfaceNumber: 0, alternate: alternate, alternates: [alternate], claimed: false };
  const configuration = { configurationValue: 1, interfaces: [usbInterface] };
  let outgoing = [],
    waiter = null,
    header = null,
    channels = new Map(),
    next = 99;
  function sendRaw(bytes) {
    if (waiter) {
      const w = waiter;
      waiter = null;
      w.resolve(bytes);
    } else outgoing.push(bytes);
  }
  function packet(cmd, arg0, arg1, payload = new Uint8Array()) {
    const num = commandId(cmd);
    // Modern ADB omits checksums after the handshake. Preserve checksums in auth traffic.
    const checksum = cmd === "CNXN" || cmd === "AUTH" ? payload.reduce((s, v) => s + v, 0) : 0;
    sendRaw(
      concatBytes(
        uint32(num),
        uint32(arg0),
        uint32(arg1),
        uint32(payload.byteLength),
        uint32(checksum),
        uint32(~num),
      ),
    );
    if (payload.byteLength) sendRaw(payload);
  }
  function shellframe(id, buf) {
    return concatBytes(Uint8Array.of(id), uint32(buf.length), buf);
  }
  const serial = "GNEWUSBTEST123";
  function scanPackages(argv) {
    let all = Object.keys(data.packages).sort();
    const f = argv.slice(3),
      filtered = f.filter((x) => x.includes(".")).at(-1);
    if (filtered) all = all.filter((n) => n.includes(filtered));
    if (f.includes("-d")) all = all.filter((n) => data.packages[n] >= 2);
    if (f.includes("-e")) all = all.filter((n) => data.packages[n] === 0 || data.packages[n] === 1);
    if (f.includes("-s")) all = all.filter((n) => !data.installed[n]);
    if (f.includes("-3")) all = all.filter((n) => data.installed[n]);
    const versions = {
      "com.google.android.gsf.login": 25,
      "com.google.android.gsf": 29,
      "com.google.android.gms": 252037022,
      "com.android.vending": 83631210,
      "com.google.android.syncadapters.calendar": 2017005136,
      "com.google.android.syncadapters.contacts": 30,
    };
    return (
      all
        .map(
          (n) =>
            "package:" + n + (f.includes("--show-versioncode") ? " versionCode:" + (versions[n] || 144) : ""),
        )
        .join("\n") + "\n"
    );
  }
  function run(argv) {
    const s = argv.join(" ");
    const last = argv.at(-1);
    if (s === "getprop")
      return (
        Object.entries(data.properties)
          .map(([k, v]) => "[" + k + "]: [" + v + "]")
          .join("\n") + "\n"
      );
    if (argv[0] === "getprop" && argv.length === 2) return (data.properties[last] || "") + "\n";
    if (s === "am get-current-user" || s === "cmd activity get-current-user")
      return String(data.selectedUser) + "\n";
    if (s.startsWith("pm list packages") || s.startsWith("cmd package list packages"))
      return scanPackages(s.startsWith("pm") ? argv : ["pm", ...argv.slice(2)]);
    if (s.startsWith("settings ")) {
      const a = argv.filter((v, i) => v !== "--user" && argv[i - 1] !== "--user");
      const [_, action, ns, key, value] = a;
      if (action === "list")
        return (
          Object.entries(data.settings[ns])
            .map(([k, v]) => k + "=" + v)
            .join("\n") + "\n"
        );
      if (action === "get") return (data.settings[ns][key] ?? "null") + "\n";
      if (action === "put" || action === "delete") {
        data.writes.push(s);
        if (action === "put") data.settings[ns][key] = value;
        else delete data.settings[ns][key];
        return "";
      }
    }
    if (s.startsWith("pm path ")) {
      if (!data.installed[last]) return "";
      return "package:/data/app/~~TestToken/" + last + "-abc/base.apk\n";
    }
    throw Error("Unimplemented benign fixture command: " + s);
  }
  function finishShell(channel, text = "", code = 0) {
    const out = concatBytes(
      ...(text ? [shellframe(code ? 2 : 1, encode(text))] : []),
      shellframe(3, Uint8Array.of(code)),
    );
    channel.queue.push(out);
    channel.end = true;
    advance(channel);
  }
  function advance(channel) {
    if (channel.waitAck) return;
    if (channel.queue.length) {
      channel.waitAck = true;
      packet("WRTE", channel.dev, channel.host, channel.queue.shift());
      return;
    }
    if (channel.end && !channel.closed) {
      channel.closed = true;
      packet("CLSE", channel.dev, channel.host);
    }
  }
  // Serve only bytes captured from the real host's earlier install stream.
  async function sendSync(channel) {
    if (channel.syncRunning || channel.waitAck) return;
    channel.syncRunning = true;
    try {
      if (channel.blob) {
        const block = channel.blob.blocks[channel.blockIndex],
          n = block ? Math.min(65536, block.length - channel.blockOffset) : 0;
        if (n) {
          const bytes = block.subarray(channel.blockOffset, channel.blockOffset + n);
          channel.blockOffset += n;
          if (channel.blockOffset >= block.length) {
            channel.blockIndex++;
            channel.blockOffset = 0;
          }
          channel.queue.push(concatBytes(encode("DATA"), uint32(n), bytes));
        } else {
          channel.queue.push(concatBytes(encode("DONE"), uint32(0)));
          channel.blob = null;
        }
      }
      advance(channel);
    } finally {
      channel.syncRunning = false;
    }
  }
  function open(channel, service) {
    if (service === "sync:") {
      channel.sync = true;
      return;
    }
    if (!service.startsWith("shell,v2,raw:")) {
      data.failures.push("Unsupported service " + service);
      channel.end = true;
      advance(channel);
      return;
    }
    const cmd = service.slice("shell,v2,raw:".length);
    const argv = (cmd.match(/(?:'[^']*'|[^\s'])+/g) || []).map((x) => x.replaceAll("'", ""));
    data.commands.push(argv.join(" "));
    channel.command = argv;
    if (
      (argv[0] === "cmd" && argv[1] === "package" && argv[2] === "install") ||
      (argv[0] === "pm" && argv[1] === "install")
    ) {
      if (!argv.includes("--user") || argv[argv.indexOf("--user") + 1] !== "0" || argv.includes("-g"))
        throw Error("Unexpected installation flags");
      channel.expect = Number(argv[argv.indexOf("-S") + 1]);
      channel.chunks = [];
      channel.size = 0;
      return;
    }
    // Real USB cannot deliver shell output before the host opens its stream.
    setTimeout(() => {
      try {
        finishShell(channel, run(argv));
      } catch (e) {
        data.failures.push(e.message);
        finishShell(channel, e.message, 1);
      }
    }, 1);
  }
  function stdin(channel, bytes) {
    channel.pending = concatBytes(channel.pending || new Uint8Array(), bytes);
    while (channel.pending.byteLength >= 5) {
      const length = readUint32(channel.pending, 1);
      if (channel.pending.byteLength < length + 5) return;
      const tag = channel.pending[0],
        body = channel.pending.subarray(5, 5 + length);
      channel.pending = channel.pending.subarray(5 + length);
      if (tag === 0 && channel.expect) {
        channel.chunks.push(body);
        channel.size += body.length;
        if (channel.size === channel.expect) {
          const id = data.filesBySize[String(channel.size)];
          if (!id) throw Error("Unknown size " + channel.size);
          data.installed[id] = { size: channel.size, blocks: channel.chunks };
          data.packages[id] = 0;
          data.installs.push(id);
          channel.chunks = [];
          finishShell(channel, "Success\n");
        }
      }
    }
  }
  async function hostPacket(h, body) {
    const [cmd, a0, a1] = h;
    if (cmd === "CNXN") {
      data.wire.push("CNXN");
      packet("AUTH", 1, 0, crypto.getRandomValues(new Uint8Array(20)));
      return;
    }
    if (cmd === "AUTH") {
      data.wire.push("AUTH:" + a0);
      if (a0 === 2) packet("AUTH", 1, 0, crypto.getRandomValues(new Uint8Array(20)));
      else if (a0 === 3) {
        if (body.length < 100) throw Error("Missing Android RSA pubkey");
        data.authKeys++;
        packet(
          "CNXN",
          0x01000001,
          1024 * 1024,
          encode(
            "device::ro.product.name=tungsten;ro.product.model=KFTUWI;ro.product.device=tungsten;features=" +
              data.features +
              ";\0",
          ),
        );
      }
      return;
    }
    if (cmd === "OPEN") {
      const channel = { dev: ++next, host: a0, queue: [], waitAck: false };
      channels.set(channel.dev, channel);
      packet("OKAY", channel.dev, channel.host);
      open(channel, decoder.decode(body).replace(/\0$/, ""));
      return;
    }
    const channel = channels.get(a1);
    if (!channel) {
      if (cmd === "CLSE") return;
      throw Error("Unknown ADB socket " + a1);
    }
    if (cmd === "CLSE") {
      if (!channel.closed) packet("CLSE", channel.dev, channel.host);
      channels.delete(channel.dev);
      return;
    }
    if (cmd === "OKAY") {
      channel.waitAck = false;
      if (channel.sync) await sendSync(channel);
      else advance(channel);
      return;
    }
    if (cmd === "WRTE") {
      packet("OKAY", channel.dev, channel.host);
      if (channel.sync) {
        channel.request = concatBytes(channel.request || new Uint8Array(), body);
        if (channel.request.length < 8) return;
        const size = readUint32(channel.request, 4);
        if (channel.request.length < 8 + size) return;
        const action = decoder.decode(channel.request.subarray(0, 4));
        const path = decoder.decode(channel.request.subarray(8, 8 + size));
        channel.request = null;
        if (action === "QUIT") return;
        if (action !== "RECV") throw Error("Unexpected sync request " + action);
        const id = Object.keys(data.installed).find((x) => path.includes("/" + x + "-"));
        if (!id) throw Error("Unknown installed path " + path);
        channel.blob = data.installed[id];
        channel.blockOffset = 0;
        channel.blockIndex = 0;
        data.reads.push(id);
        await sendSync(channel);
      } else stdin(channel, body);
      return;
    }
    throw Error("Unexpected host command " + cmd);
  }
  const dev = {
    vendorId: 0x1949,
    productId: 0x0001,
    productName: "QA Fire",
    serialNumber: serial,
    configurations: [configuration],
    configuration: configuration,
    opened: false,
    async open() {
      data.offline = false;
      this.opened = true;
    },
    async claimInterface() {
      usbInterface.claimed = true;
    },
    async selectConfiguration() {},
    async selectAlternateInterface() {},
    async close() {
      data.offline = true;
      this.opened = false;
      usbInterface.claimed = false;
      if (waiter) {
        waiter.reject(new DOMException("Disconnected", "NetworkError"));
        waiter = null;
      }
      header = null;
      channels.clear();
      outgoing = [];
    },
    async transferIn() {
      if (data.offline) throw new DOMException("Disconnected", "NetworkError");
      const v = outgoing.length
        ? outgoing.shift()
        : await new Promise((resolve, reject) => {
            waiter = { resolve, reject };
          });
      return { status: "ok", data: new DataView(v.slice().buffer) };
    },
    async transferOut(ep, buf) {
      const bytes = new Uint8Array(buf.buffer ?? buf, buf.byteOffset ?? 0, buf.byteLength);
      try {
        if (bytes.length) {
          if (header) {
            const h = header;
            header = null;
            if (bytes.length !== h[3]) throw Error("Wrong ADB payload length");
            await hostPacket(h, bytes);
          } else {
            if (bytes.length !== 24) throw Error("Bad host packet header length " + bytes.length);
            const h = [
              decoder.decode(bytes.subarray(0, 4)),
              readUint32(bytes, 4),
              readUint32(bytes, 8),
              readUint32(bytes, 12),
            ];
            if (h[3]) header = h;
            else await hostPacket(h, new Uint8Array());
          }
        }
      } catch (e) {
        data.failures.push(e.message);
        throw e;
      }
      return { status: "ok", bytesWritten: bytes.length };
    },
  };
  usb.requestDevice = async (options) => {
    data.requests.push(options);
    data.chooserCount++;
    if (data.cancel) throw new DOMException("Cancelled", "NotFoundError");
    return dev;
  };
  usb.getDevices = async () => (dev.opened ? [dev] : []);
  Object.defineProperty(navigator, "usb", { value: usb, configurable: true });
  data.unplug = async () => {
    await dev.close();
    const e = new Event("disconnect");
    Object.defineProperty(e, "device", { value: dev });
    usb.dispatchEvent(e);
  };
})();
