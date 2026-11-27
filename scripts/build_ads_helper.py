#!/usr/bin/env python3
"""Build and sign the optional Android helper with local SDK and JDK tools."""

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


COMPANION = Path(__file__).resolve().parents[1] / "companion"
BUILD_DIR = COMPANION / "build"
MIN_ANDROID_API = "24"
JAVA_INPUTS = tuple("src/org/firetools/adshelper/" + name + ".java" for name in
                    ("AdsService", "AdsState", "BootReceiver", "HelperSettings", "MainActivity"))
JAVA_ENV_OPTIONS = {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS", "CLASSPATH"}
DEVELOPMENT_ALIAS = "fire-tools-development"
DEVELOPMENT_PASSWORD_VAR = "FIRE_TOOLS_LOCAL_DEVELOPMENT_KEY_PASSWORD"


@dataclass(frozen=True)
class Tools:
    android_jar: Path
    aapt2: Path
    d8: Path
    zipalign: Path
    apksigner: Path
    java: Path
    javac: Path
    keytool: Path | None


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT"),
                        help="Installed Android SDK root (defaults to ANDROID_HOME or ANDROID_SDK_ROOT)")
    parser.add_argument("--build-tools-version", default="36.0.0", help="Installed Build Tools version")
    parser.add_argument("--android-api", type=int, default=36, help="Installed Android compile API level")
    parser.add_argument("--java-home", type=Path, default=os.environ.get("JAVA_HOME"), help="JDK root")
    parser.add_argument("--output", type=Path, default=BUILD_DIR / "fire-tools-ads-helper.apk",
                        help="New output .apk path")
    parser.add_argument("--keystore", type=Path, help="Use an existing private signing keystore")
    parser.add_argument("--key-alias", help="Alias in the existing keystore")
    parser.add_argument("--storepass-env", metavar="NAME", help="Environment variable holding the keystore password")
    parser.add_argument("--keypass-env", metavar="NAME", help="Environment variable holding the key password")
    args = parser.parse_args(argv)

    if args.sdk is None:
        parser.error("Supply an installed Android SDK using --sdk or ANDROID_HOME.")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-rc\d+)?", args.build_tools_version, re.ASCII):
        parser.error("Use a numeric build-tools version, such as 36.0.0.")
    if args.android_api < 28:
        parser.error("Use an Android compile API of at least 28.")
    if args.output.suffix.lower() != ".apk":
        parser.error("The output filename must end in .apk.")
    if args.keystore and not args.key_alias:
        parser.error("An existing --keystore requires --key-alias.")
    if not args.keystore and (args.key_alias or args.storepass_env or args.keypass_env):
        parser.error("Custom signing options require --keystore.")
    for env_name in (args.storepass_env, args.keypass_env):
        if env_name is not None and env_name not in os.environ:
            parser.error(f"Signing password environment variable {env_name!r} is unset.")
    return args


def require_file(path, label, *, executable=False):
    if not path.is_file() or not os.access(path, os.X_OK if executable else os.R_OK):
        raise ValueError(f"Missing or inaccessible {label}: {path}")
    if executable and os.name == "nt" and path.resolve(strict=True).suffix.lower() != ".exe":
        raise ValueError(f"Choose a native Windows executable for {label}: {path}")
    return path


def build_input(relative):
    path = COMPANION / relative
    if path.resolve(strict=True) != path:
        raise ValueError(f"Helper build input must not be a symlink: {path}")
    return require_file(path, "helper source file")


def resolve_tools(args):
    sdk = args.sdk.expanduser().resolve()
    platform = sdk / "platforms" / f"android-{args.android_api}"
    build_tools = sdk / "build-tools" / args.build_tools_version
    suffix = ".exe" if os.name == "nt" else ""

    def jdk_tool(name):
        if args.java_home:
            path = args.java_home.expanduser().resolve() / "bin" / f"{name}{suffix}"
        else:
            # Search explicit, absolute PATH entries for the actual binary. Windows
            # executable lookup can otherwise select a current-directory file or batch wrapper.
            current = Path.cwd().resolve()
            for folder in map(Path, os.get_exec_path()):
                if not folder.is_absolute() or folder.resolve() == current:
                    continue
                path = folder / f"{name}{suffix}"
                if path.is_file() and os.access(path, os.X_OK):
                    break
            else:
                raise ValueError(f"JDK tool {name} is missing. Set --java-home or JAVA_HOME.")
        return require_file(path, f"JDK {name}", executable=True)

    return Tools(
        android_jar=require_file(platform / "android.jar", "platform android.jar"),
        aapt2=require_file(build_tools / f"aapt2{suffix}", "SDK aapt2", executable=True),
        d8=require_file(build_tools / "lib" / "d8.jar", "SDK d8.jar"),
        zipalign=require_file(build_tools / f"zipalign{suffix}", "SDK zipalign", executable=True),
        apksigner=require_file(build_tools / "lib" / "apksigner.jar", "SDK apksigner.jar"),
        java=jdk_tool("java"),
        javac=jdk_tool("javac"),
        keytool=jdk_tool("keytool") if args.keystore is None else None,
    )


def run(command, *, env=None, capture_output=False):
    environment = {key: value for key, value in (os.environ if env is None else env).items()
                   if key.upper() not in JAVA_ENV_OPTIONS}
    completed = subprocess.run(
        list(map(os.fspath, command)), shell=False, check=False, text=True,
        env=environment, timeout=180, stdout=subprocess.PIPE if capture_output else None,
    )
    if completed.returncode:
        if capture_output and completed.stdout:
            print(completed.stdout, file=sys.stderr, end="")
        raise ValueError(f"{Path(command[0]).name} returned exit code {completed.returncode}.")
    return completed.stdout


def development_keystore(keytool, environment):
    BUILD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory_info = BUILD_DIR.lstat()
    if not stat.S_ISDIR(directory_info.st_mode):
        raise ValueError(f"Use a regular directory for the local development key: {BUILD_DIR}")
    if os.name == "posix" and (directory_info.st_uid != os.geteuid() or directory_info.st_mode & 0o022):
        raise ValueError(f"The signing directory must be owned by you and writable only by you: {BUILD_DIR}")

    keystore = BUILD_DIR / "ads-helper-development.p12"
    if not os.path.lexists(keystore):
        with tempfile.TemporaryDirectory(prefix=".signing-", dir=BUILD_DIR) as directory:
            pending = Path(directory) / "key.p12"
            run([
                keytool, "-genkeypair", "-keystore", pending, "-storetype", "PKCS12",
                "-alias", DEVELOPMENT_ALIAS, "-dname", "CN=Fire Tools Local Development",
                "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650",
                "-storepass:env", DEVELOPMENT_PASSWORD_VAR,
            ], env=environment)
            pending.chmod(0o600)
            try:
                os.link(pending, keystore)
            except FileExistsError:
                # A concurrent build may have installed the local key first.
                pass
    key_info = keystore.lstat()
    if not stat.S_ISREG(key_info.st_mode):
        raise ValueError(f"The local development keystore must be a regular file: {keystore}")
    if os.name == "posix" and (key_info.st_uid != os.geteuid() or key_info.st_mode & 0o066):
        raise ValueError(f"The local development keystore must be private to your account: {keystore}")
    return require_file(keystore, "local development keystore")


def signing_options(args, tools):
    if args.keystore:
        keystore = require_file(args.keystore.expanduser().resolve(), "existing keystore")
        options = ["--ks", keystore, "--ks-key-alias", args.key_alias]
        if args.storepass_env:
            options.extend(["--ks-pass", f"env:{args.storepass_env}"])
        if args.keypass_env:
            options.extend(["--key-pass", f"env:{args.keypass_env}"])
        return options, None

    environment = dict(os.environ, **{DEVELOPMENT_PASSWORD_VAR: "android"})
    keystore = development_keystore(tools.keytool, environment)
    return [
        "--ks", keystore, "--ks-key-alias", DEVELOPMENT_ALIAS,
        "--ks-pass", f"env:{DEVELOPMENT_PASSWORD_VAR}",
    ], environment


def build(args):
    output = args.output.expanduser().absolute()
    if os.path.lexists(output):
        raise ValueError(f"Output already exists: {output}")

    tools = resolve_tools(args)
    output.parent.mkdir(mode=0o700 if output.parent == BUILD_DIR else 0o777, parents=True, exist_ok=True)
    sources = [build_input(name) for name in JAVA_INPUTS]
    manifest = build_input("AndroidManifest.xml")

    with tempfile.TemporaryDirectory(prefix=".ads-helper-", dir=output.parent) as directory:
        stage = Path(directory)
        classes = stage / "classes"
        dex = stage / "dex"
        classes.mkdir()
        dex.mkdir()
        unsigned = stage / "unsigned.apk"
        aligned = stage / "aligned.apk"
        signed = stage / "signed.apk"

        # A separate empty source path confines compilation to the named inputs.
        sourcepath = stage / "empty-sourcepath"
        sourcepath.mkdir()
        run([tools.javac, "--release", "8", "-proc:none", "-sourcepath", sourcepath,
             "-encoding", "UTF-8", "-classpath", tools.android_jar, "-d", classes, *sources])
        run([tools.java, "-cp", tools.d8, "com.android.tools.r8.D8", "--min-api", MIN_ANDROID_API,
             "--lib", tools.android_jar, "--output", dex, *sorted(classes.rglob("*.class"))])
        run([tools.aapt2, "link", "-o", unsigned, "--manifest", manifest, "-I", tools.android_jar])
        with zipfile.ZipFile(unsigned, "a", compression=zipfile.ZIP_DEFLATED) as apk:
            apk.write(dex / "classes.dex", "classes.dex")
        run([tools.zipalign, "-f", "4", unsigned, aligned])

        sign_options, sign_env = signing_options(args, tools)
        signer = [tools.java, "-jar", tools.apksigner]
        run([*signer, "sign", "--v4-signing-enabled", "false", "--out", signed, *sign_options, aligned], env=sign_env)
        verification = run([*signer, "verify", "--print-certs", signed], capture_output=True)
        fingerprints = [line for line in verification.splitlines() if "certificate SHA-256 digest:" in line]
        if not fingerprints:
            raise ValueError("APK signature verified without a reported SHA-256 certificate fingerprint.")
        run([tools.zipalign, "-c", "4", signed])
        with signed.open("rb") as apk:
            digest = hashlib.file_digest(apk, "sha256").hexdigest()

        try:
            os.link(signed, output)
        except FileExistsError as error:
            raise ValueError(f"Output already exists: {output}") from error

    print(f"APK: {output}")
    print(f"APK SHA-256: {digest}")
    print("\n".join(fingerprints))


def main(argv=None):
    args = parse_args(argv)
    try:
        build(args)
    except subprocess.TimeoutExpired as error:
        print(f"Build failed: {Path(error.cmd[0]).name} timed out.", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
