import {connectUsb} from "./adb-transport.js";
import {bindDevice} from "./browser-session.mjs";
import {readInstalledPackages} from "./browser-report.mjs";
export {withDeviceLock} from "./browser-session.mjs";

export async function connectDevice(signal) {
  const raw = await connectUsb(signal);
  const cancel = () => { Promise.resolve(raw.close()).catch(() => {}); };
  try {
    signal?.addEventListener("abort", cancel, {once: true});
    signal?.throwIfAborted();
    const session = await bindDevice(raw);
    signal?.throwIfAborted();
    return session;
  } catch (error) {
    await Promise.resolve(raw.close()).catch(() => {});
    throw error;
  } finally {
    signal?.removeEventListener("abort", cancel);
  }
}

export async function readInventory(session) {
  return (await readInstalledPackages(session)).map(entry => entry.package + " · " + entry.state);
}
