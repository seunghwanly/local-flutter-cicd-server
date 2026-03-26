from __future__ import annotations

import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from src.core import BuildRuntimeContext
from src.internal.infrastructure.command_runner import CompletedCommand
from src.internal.infrastructure.setup_executor import SetupExecutor


class FakeCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.responses: dict[tuple[str, ...], list[CompletedCommand]] = defaultdict(list)

    def add_response(self, command: list[str], returncode: int = 0, stdout: str = "") -> None:
        self.responses[tuple(command)].append(
            CompletedCommand(args=command, returncode=returncode, stdout=stdout)
        )

    def run(self, command, *, env, cwd, check=True, should_stop=None):
        self.calls.append(tuple(command))
        queue = self.responses.get(tuple(command), [])
        if queue:
            return queue.pop(0)
        return CompletedCommand(args=list(command), returncode=0, stdout="")

    def run_checked(self, command, *, env, cwd, should_stop=None):
        result = self.run(command, env=env, cwd=cwd, check=True, should_stop=should_stop)
        if result.returncode != 0:
            raise RuntimeError(f"unexpected failure for {' '.join(command)}")
        return result


def create_flutter_ios_artifact(repo_dir: Path) -> None:
    artifact_dir = repo_dir / ".fvm" / "flutter_sdk" / "bin" / "cache" / "artifacts" / "engine" / "ios" / "Flutter.xcframework"
    artifact_dir.mkdir(parents=True, exist_ok=True)


def default_ios_env(**overrides: str) -> dict[str, str]:
    env = {
        "GEM_HOME": "/tmp/gems",
        "KEYCHAIN_NAME": "login.keychain",
        "KEYCHAIN_PASSWORD": "secret",
        "MATCH_PASSWORD": "match-secret",
        "APPSTORE_API_KEY_ID": "key-id",
        "APPSTORE_ISSUER_ID": "issuer-id",
        "APPSTORE_API_PRIVATE_KEY": "private-key",
    }
    env.update(overrides)
    return env


def register_login_keychain(
    runner: FakeCommandRunner,
    home: Path,
    *,
    password: str = "secret",
    listed: bool = True,
) -> Path:
    keychain_dir = home / "Library" / "Keychains"
    keychain_dir.mkdir(parents=True, exist_ok=True)
    keychain_path = keychain_dir / "login.keychain-db"
    keychain_path.write_text("", encoding="utf-8")

    if listed:
        runner.add_response(
            ["security", "list-keychains", "-d", "user"],
            stdout=f"    \"{keychain_path.resolve()}\"\n",
        )
    else:
        runner.add_response(["security", "list-keychains", "-d", "user"], stdout="    \"/tmp/other.keychain-db\"\n")
        runner.add_response(
            ["security", "list-keychains", "-d", "user", "-s", "/tmp/other.keychain-db", str(keychain_path.resolve())]
        )
    runner.add_response(["security", "default-keychain", "-d", "user"], stdout=f"    \"{keychain_path.resolve()}\"\n")
    runner.add_response(["security", "unlock-keychain", "-p", password, str(keychain_path.resolve())])
    runner.add_response([
        "security", "set-key-partition-list",
        "-S", "apple-tool:,apple:,codesign:",
        "-s", "-k", password, str(keychain_path.resolve()),
    ])
    runner.add_response(["security", "set-keychain-settings", "-lut", "21600", str(keychain_path.resolve())])
    runner.add_response(["security", "default-keychain", "-d", "user", "-s", str(keychain_path.resolve())])
    return keychain_path


class SetupExecutorTests(unittest.TestCase):
    def test_run_setup_repairs_cache_and_retries_pub_get_without_melos(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["fvm", "dart", "pub", "global", "activate", "melos"])
        runner.add_response(["fvm", "dart", "pub", "global", "activate", "flutterfire_cli"])
        runner.add_response(
            ["fvm", "flutter", "pub", "get", "--verbose"],
            returncode=1,
            stdout="pub get failed",
        )
        runner.add_response(["fvm", "flutter", "pub", "cache", "repair"], stdout="repair ok")
        runner.add_response(["fvm", "flutter", "pub", "get", "--verbose"], stdout="pub get ok")

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            pub_cache = Path(tmp) / "pub_cache"
            repo_dir.mkdir()
            (repo_dir / "pubspec.yaml").write_text("name: sample\n", encoding="utf-8")
            (pub_cache / "git" / "cache").mkdir(parents=True)

            executor.run_setup(
                build_id="build-1",
                context=BuildRuntimeContext(
                    env={"PUB_CACHE": str(pub_cache)},
                    repo_dir=str(repo_dir),
                    workspace=tmp,
                ),
                log=logs.append,
            )

        self.assertIn(("fvm", "flutter", "pub", "cache", "repair"), runner.calls)
        self.assertEqual(
            2,
            runner.calls.count(("fvm", "flutter", "pub", "get", "--verbose")),
        )
        self.assertTrue(any("Dependency resolution recovered" in line for line in logs))

    def test_run_setup_uses_melos_only_when_workspace_file_exists(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        runner.add_response(["fvm", "dart", "pub", "global", "activate", "melos"])
        runner.add_response(["fvm", "dart", "pub", "global", "activate", "flutterfire_cli"])
        runner.add_response(["fvm", "exec", "melos", "run", "pub"], stdout="melos ok")

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            pub_cache = Path(tmp) / "pub_cache"
            repo_dir.mkdir()
            (repo_dir / "pubspec.yaml").write_text("name: sample\n", encoding="utf-8")
            (repo_dir / "melos.yaml").write_text("name: workspace\n", encoding="utf-8")
            (pub_cache / "git" / "cache").mkdir(parents=True)

            executor.run_setup(
                build_id="build-melos",
                context=BuildRuntimeContext(
                    env={"PUB_CACHE": str(pub_cache)},
                    repo_dir=str(repo_dir),
                    workspace=tmp,
                ),
                log=lambda _: None,
            )

        self.assertIn(("fvm", "exec", "melos", "run", "pub"), runner.calls)

    def test_prepare_ios_toolchain_uses_bundler_when_gemfile_exists(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.1.0\n3.2.0\n3.3.9\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
        runner.add_response(["gem", "list", "-i", "cocoapods", "-v", "1.16.2"], returncode=0)
        runner.add_response(["gem", "list", "-i", "bundler", "-v", "2.7.2"], returncode=0)
        runner.add_response(["bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/ruby-3.2.0/bundle"])
        runner.add_response(["bundle", "_2.7.2_", "install"], stdout="bundle ok")

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            (ios_dir / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
            (ios_dir / "Gemfile.lock").write_text(
                "GEM\n"
                "  specs:\n"
                "\n"
                "RUBY VERSION\n"
                "   ruby 3.2.0p0\n"
                "\n"
                "BUNDLED WITH\n"
                "   2.7.2\n",
                encoding="utf-8",
            )
            create_flutter_ios_artifact(repo_dir)
            register_login_keychain(runner, Path(home))

            context = BuildRuntimeContext(
                env=default_ios_env(COCOAPODS_VERSION="1.16.2"),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-ios",
                    platform="ios",
                    context=context,
                    log=logs.append,
                )

        self.assertIn(("gem", "list", "-i", "cocoapods", "-v", "1.16.2"), runner.calls)
        self.assertIn(("gem", "list", "-i", "bundler", "-v", "2.7.2"), runner.calls)
        self.assertIn(("bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/ruby-3.2.0/bundle"), runner.calls)
        self.assertIn(("bundle", "_2.7.2_", "install"), runner.calls)
        self.assertTrue(any("Installing Ruby bundle" in line for line in logs))
        self.assertEqual("login.keychain-db", context.env["KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["KEYCHAIN_PASSWORD"])
        self.assertEqual("login.keychain-db", context.env["MATCH_KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["MATCH_KEYCHAIN_PASSWORD"])
        self.assertEqual("/tmp/gems/ruby-3.2.0", context.env["GEM_HOME"])
        self.assertEqual("/tmp/gems/ruby-3.2.0/bundle", context.env["BUNDLE_PATH"])
        self.assertEqual("true", context.env["IOS_SHOULD_RUN_POD_INSTALL"])
        self.assertEqual(0, len(context.cleanup_callbacks))

    def test_prepare_ios_toolchain_exports_fastlane_match_keychain_env(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
        runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
        runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)
            keychain_path = register_login_keychain(runner, Path(home))

            context = BuildRuntimeContext(
                env=default_ios_env(),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-match-keychain",
                    platform="ios",
                    context=context,
                    log=logs.append,
                )

        self.assertEqual(keychain_path.name, context.env["MATCH_KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["MATCH_KEYCHAIN_PASSWORD"])
        self.assertEqual(keychain_path.name, context.env["KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["KEYCHAIN_PASSWORD"])
        self.assertEqual(0, len(context.cleanup_callbacks))
        self.assertTrue(any("Fastlane match will use keychain" in line for line in logs))

    def test_prepare_ios_toolchain_prepares_standalone_fastlane_for_shorebird_patch(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
        runner.add_response(["gem", "list", "-i", "cocoapods", "-v", "1.16.2"], returncode=0)
        runner.add_response(["gem", "list", "-i", "bundler", "-v", "2.7.2"], returncode=0)
        runner.add_response(["bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/ruby-3.2.0/bundle"])
        runner.add_response(["bundle", "_2.7.2_", "install"], stdout="bundle ok")
        runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)
        runner.add_response(["gem", "list", "-i", "fastlane-plugin-shorebird"], returncode=0)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            fastlane_dir = ios_dir / "fastlane"
            fastlane_dir.mkdir(parents=True)
            (ios_dir / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
            (ios_dir / "Gemfile.lock").write_text(
                "GEM\n"
                "  specs:\n"
                "\n"
                "RUBY VERSION\n"
                "   ruby 3.2.0p0\n"
                "\n"
                "BUNDLED WITH\n"
                "   2.7.2\n",
                encoding="utf-8",
            )
            (fastlane_dir / "Pluginfile").write_text(
                "gem 'fastlane-plugin-shorebird'\n",
                encoding="utf-8",
            )
            create_flutter_ios_artifact(repo_dir)
            register_login_keychain(runner, Path(home))

            context = BuildRuntimeContext(
                env=default_ios_env(COCOAPODS_VERSION="1.16.2"),
                repo_dir=str(repo_dir),
                workspace=tmp,
                trigger_source="shorebird_manual",
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-ios-shorebird",
                    platform="ios",
                    context=context,
                    log=lambda _: None,
                )

        self.assertIn(("bundle", "_2.7.2_", "install"), runner.calls)
        self.assertIn(("gem", "list", "-i", "fastlane"), runner.calls)
        self.assertIn(("gem", "list", "-i", "fastlane-plugin-shorebird"), runner.calls)

    def test_prepare_android_toolchain_uses_ruby_version_fallback(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.1.0\n3.3.9\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.3.9")
        runner.add_response(["gem", "list", "-i", "bundler", "-v", "2.7.2"], returncode=0)
        runner.add_response(["bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/ruby-3.3.9/bundle"])
        runner.add_response(["bundle", "_2.7.2_", "install"], stdout="bundle ok")

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            android_dir = repo_dir / "android"
            android_dir.mkdir(parents=True)
            (android_dir / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
            (android_dir / "Gemfile.lock").write_text(
                "GEM\n"
                "  specs:\n"
                "\n"
                "BUNDLED WITH\n"
                "   2.7.2\n",
                encoding="utf-8",
            )

            context = BuildRuntimeContext(
                env={"GEM_HOME": "/tmp/gems", "RUBY_VERSION": "3.2.0"},
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            executor.prepare_platform_toolchain(
                build_id="build-android",
                platform="android",
                context=context,
                log=logs.append,
            )

        self.assertIn(("bundle", "_2.7.2_", "install"), runner.calls)
        self.assertTrue(any("Using compatible installed Ruby 3.3.9 for RUBY_VERSION requirement 3.2.0+" in line for line in logs))
        self.assertEqual("/tmp/gems/ruby-3.3.9", context.env["GEM_HOME"])
        self.assertEqual("/tmp/gems/ruby-3.3.9/bundle", context.env["BUNDLE_PATH"])

    def test_prepare_ios_toolchain_unlocks_configured_keychain(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            keychain_path = register_login_keychain(runner, Path(home), listed=False)
            runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
            runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
            runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
            runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)
            context = BuildRuntimeContext(
                env=default_ios_env(),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-keychain",
                    platform="ios",
                    context=context,
                    log=logs.append,
                )

        self.assertIn(("security", "set-keychain-settings", "-lut", "21600", str(keychain_path.resolve())), runner.calls)
        self.assertIn(("security", "unlock-keychain", "-p", "secret", str(keychain_path.resolve())), runner.calls)
        self.assertIn(
            (
                "security",
                "set-key-partition-list",
                "-S",
                "apple-tool:,apple:,codesign:",
                "-s",
                "-k",
                "secret",
                str(keychain_path.resolve()),
            ),
            runner.calls,
        )
        self.assertIn(("security", "default-keychain", "-d", "user", "-s", str(keychain_path.resolve())), runner.calls)
        self.assertNotIn("KEYCHAIN_PATH", context.env)
        self.assertEqual("login.keychain-db", context.env["KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["KEYCHAIN_PASSWORD"])
        self.assertEqual("login.keychain-db", context.env["MATCH_KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["MATCH_KEYCHAIN_PASSWORD"])
        self.assertTrue(any("Keychain ready" in line for line in logs))

    def test_prepare_ios_toolchain_fails_when_login_keychain_unlock_fails(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            keychain_dir = Path(home) / "Library" / "Keychains"
            keychain_dir.mkdir(parents=True, exist_ok=True)
            keychain_path = keychain_dir / "login.keychain-db"
            keychain_path.write_text("", encoding="utf-8")
            runner.add_response(["security", "list-keychains", "-d", "user"], stdout="    \"/tmp/other.keychain-db\"\n")
            runner.add_response(
                ["security", "list-keychains", "-d", "user", "-s", "/tmp/other.keychain-db", str(keychain_path.resolve())]
            )
            runner.add_response(
                ["security", "unlock-keychain", "-p", "wrong-secret", str(keychain_path.resolve())],
                returncode=51,
                stdout="security: unlock failed",
            )
            runner.add_response(["security", "set-keychain-settings", "-lut", "21600", str(keychain_path.resolve())])
            runner.add_response(["security", "default-keychain", "-d", "user", "-s", str(keychain_path.resolve())])
            runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
            runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
            runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
            runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)
            context = BuildRuntimeContext(
                env=default_ios_env(KEYCHAIN_PASSWORD="wrong-secret"),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                with self.assertRaises(RuntimeError):
                    executor.prepare_platform_toolchain(
                        build_id="build-keychain-fallback",
                        platform="ios",
                        context=context,
                        log=lambda _: None,
                    )

        self.assertNotIn(("security", "default-keychain", "-d", "user", "-s", str(keychain_path.resolve())), runner.calls)
        self.assertEqual("login.keychain", context.env["KEYCHAIN_NAME"])
        self.assertEqual("wrong-secret", context.env["KEYCHAIN_PASSWORD"])
        self.assertNotIn("MATCH_KEYCHAIN_NAME", context.env)
        self.assertNotIn("MATCH_KEYCHAIN_PASSWORD", context.env)

    def test_prepare_ios_toolchain_fails_when_configured_keychain_password_missing(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            register_login_keychain(runner, Path(home))
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)

            context = BuildRuntimeContext(
                env=default_ios_env(KEYCHAIN_PASSWORD=""),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "KEYCHAIN_PASSWORD is required for configured iOS keychains",
                ):
                    executor.prepare_platform_toolchain(
                        build_id="build-missing-keychain-password",
                        platform="ios",
                        context=context,
                        log=lambda _: None,
                    )

        self.assertNotIn("MATCH_KEYCHAIN_NAME", context.env)
        self.assertNotIn("MATCH_KEYCHAIN_PASSWORD", context.env)

    def test_prepare_ios_toolchain_creates_custom_keychain_when_missing(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)

            custom_keychain = Path(home) / "Library" / "Keychains" / "ppb_ci_signing.keychain-db"
            runner.add_response(["security", "default-keychain", "-d", "user"], stdout="    \"/tmp/original.keychain-db\"\n")
            runner.add_response(["security", "list-keychains", "-d", "user"], stdout="")
            runner.add_response(["security", "list-keychains", "-d", "user", "-s", str(custom_keychain)])
            runner.add_response(["security", "unlock-keychain", "-p", "secret", str(custom_keychain)])
            runner.add_response([
                "security", "set-key-partition-list",
                "-S", "apple-tool:,apple:,codesign:",
                "-s", "-k", "secret", str(custom_keychain),
            ])
            runner.add_response(["security", "set-keychain-settings", "-lut", "21600", str(custom_keychain)])
            runner.add_response(["security", "default-keychain", "-d", "user", "-s", str(custom_keychain)])
            runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
            runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
            runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
            runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

            context = BuildRuntimeContext(
                env=default_ios_env(KEYCHAIN_NAME="ppb_ci_signing", MATCH_PASSWORD="match-secret"),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-custom-keychain",
                    platform="ios",
                    context=context,
                    log=logs.append,
                )

        self.assertNotIn(("security", "create-keychain", "-p", "secret", str(custom_keychain)), runner.calls)
        self.assertNotIn("KEYCHAIN_PATH", context.env)
        self.assertEqual("ppb_ci_signing.keychain-db", context.env["KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["KEYCHAIN_PASSWORD"])
        self.assertEqual("ppb_ci_signing.keychain-db", context.env["MATCH_KEYCHAIN_NAME"])
        self.assertEqual("secret", context.env["MATCH_KEYCHAIN_PASSWORD"])
        self.assertTrue(any("Fastlane match will use keychain" in line for line in logs))

    def test_prepare_ios_toolchain_creates_ephemeral_keychain_when_name_missing(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            create_flutter_ios_artifact(repo_dir)
            ephemeral_path = (Path(tmp) / "keychains" / "build-ephemeral.keychain-db").resolve()
            runner.add_response(["security", "default-keychain", "-d", "user"], stdout="    \"/tmp/original.keychain-db\"\n")
            runner.add_response(["security", "set-keychain-settings", "-lut", "21600", str(ephemeral_path)])
            runner.add_response(["security", "list-keychains", "-d", "user"], stdout="    \"/tmp/original.keychain-db\"\n")
            runner.add_response(["security", "list-keychains", "-d", "user", "-s", "/tmp/original.keychain-db", str(ephemeral_path)])
            runner.add_response(["security", "default-keychain", "-d", "user", "-s", str(ephemeral_path)])
            runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
            runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
            runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
            runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

            context = BuildRuntimeContext(
                env=default_ios_env(KEYCHAIN_NAME="", KEYCHAIN_PASSWORD=""),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )
            executor.prepare_platform_toolchain(
                build_id="build-ephemeral",
                platform="ios",
                context=context,
                log=logs.append,
            )

        self.assertEqual(str(ephemeral_path), context.env["KEYCHAIN_NAME"])
        self.assertEqual(str(ephemeral_path), context.env["MATCH_KEYCHAIN_NAME"])
        self.assertTrue(context.env["KEYCHAIN_PASSWORD"])
        self.assertTrue(context.env["MATCH_KEYCHAIN_PASSWORD"])
        self.assertEqual(1, len(context.cleanup_callbacks))
        self.assertTrue(any("Created ephemeral keychain" in line for line in logs))

    def test_prepare_ios_toolchain_repairs_missing_flutter_artifact_before_fastlane(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            repo_dir = Path(tmp) / "repo"
            ios_dir = repo_dir / "ios"
            ios_dir.mkdir(parents=True)
            register_login_keychain(runner, Path(home))
            runner.add_response(["fvm", "flutter", "precache", "--ios"])
            runner.add_response(["rbenv", "versions", "--bare"], stdout="3.2.0\n")
            runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.2.0")
            runner.add_response(["gem", "list", "-i", "cocoapods"], returncode=0)
            runner.add_response(["gem", "list", "-i", "fastlane"], returncode=0)

            context = BuildRuntimeContext(
                env=default_ios_env(IOS_RUN_POD_INSTALL="false"),
                repo_dir=str(repo_dir),
                workspace=tmp,
            )

            with patch("pathlib.Path.home", return_value=Path(home)):
                executor.prepare_platform_toolchain(
                    build_id="build-precache-ios",
                    platform="ios",
                    context=context,
                    log=lambda _: None,
                )

        self.assertIn(("fvm", "flutter", "precache", "--ios"), runner.calls)
        self.assertEqual("true", context.env["IOS_FLUTTER_SDK_CHANGED"])

    def test_prepare_android_toolchain_fails_when_lockfile_requires_newer_ruby(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.1.0\n3.3.9\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.1.0")

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            android_dir = repo_dir / "android"
            android_dir.mkdir(parents=True)
            (android_dir / "Gemfile").write_text("source 'https://rubygems.org'\n", encoding="utf-8")
            (android_dir / "Gemfile.lock").write_text(
                "GEM\n"
                "  specs:\n"
                "\n"
                "RUBY VERSION\n"
                "   ruby 3.2.0p0\n"
                "\n"
                "BUNDLED WITH\n"
                "   2.7.2\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "Gemfile.lock requires Ruby 3.2.0\\+ but active Ruby is 3.1.0"):
                executor.prepare_platform_toolchain(
                    build_id="build-android",
                    platform="android",
                    context=BuildRuntimeContext(
                        env={"GEM_HOME": "/tmp/gems"},
                        repo_dir=str(repo_dir),
                        workspace=tmp,
                    ),
                    log=lambda _: None,
                )

    def test_prepare_android_toolchain_clears_shorebird_cache_when_patch_binary_arch_mismatches(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["shorebird", "cache", "clean"], stdout="cache cleaned")

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo"
            android_dir = repo_dir / "android"
            android_dir.mkdir(parents=True)

            patch_binary = Path("/tmp/shorebird/bin/cache/artifacts/patch/patch").resolve()
            patch_binary.parent.mkdir(parents=True, exist_ok=True)
            patch_binary.write_text("", encoding="utf-8")

            runner.add_response(
                ["file", str(patch_binary)],
                stdout=f"{patch_binary}: Mach-O 64-bit executable x86_64",
            )
            with (
                patch("shutil.which", return_value="/tmp/shorebird/bin/shorebird"),
                patch("platform.machine", return_value="arm64"),
            ):
                executor.prepare_platform_preflight(
                    build_id="build-shorebird",
                    platform="android",
                    context=BuildRuntimeContext(
                        env={"GEM_HOME": "/tmp/gems", "PATH": "/tmp/shorebird/bin:/usr/bin"},
                        repo_dir=str(repo_dir),
                        workspace=tmp,
                        trigger_source="shorebird_manual",
                    ),
                    log=logs.append,
                )

        self.assertIn(("shorebird", "cache", "clean"), runner.calls)
        self.assertTrue(any("architecture mismatch" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
