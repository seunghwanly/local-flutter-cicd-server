from __future__ import annotations

import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from src.infrastructure.command_runner import CompletedCommand
from src.infrastructure.setup_executor import SetupExecutor


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
                repo_dir=str(repo_dir),
                env={"PUB_CACHE": str(pub_cache)},
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
                repo_dir=str(repo_dir),
                env={"PUB_CACHE": str(pub_cache)},
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
        runner.add_response(["bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/bundle"])
        runner.add_response(["bundle", "_2.7.2_", "install"], stdout="bundle ok")

        with tempfile.TemporaryDirectory() as tmp:
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

            executor.prepare_platform_toolchain(
                build_id="build-ios",
                platform="ios",
                repo_dir=str(repo_dir),
                env={"GEM_HOME": "/tmp/gems", "COCOAPODS_VERSION": "1.16.2"},
                log=logs.append,
            )

        self.assertIn(("gem", "list", "-i", "cocoapods", "-v", "1.16.2"), runner.calls)
        self.assertIn(("gem", "list", "-i", "bundler", "-v", "2.7.2"), runner.calls)
        self.assertIn(("bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/bundle"), runner.calls)
        self.assertIn(("bundle", "_2.7.2_", "install"), runner.calls)
        self.assertTrue(any("Installing Ruby bundle" in line for line in logs))

    def test_prepare_android_toolchain_uses_ruby_version_fallback(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)
        logs: list[str] = []

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.1.0\n3.3.9\n")
        runner.add_response(["ruby", "-e", "print RUBY_VERSION"], stdout="3.3.9")
        runner.add_response(["gem", "list", "-i", "bundler", "-v", "2.7.2"], returncode=0)
        runner.add_response(["bundle", "_2.7.2_", "config", "set", "--local", "path", "/tmp/gems/bundle"])
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

            executor.prepare_platform_toolchain(
                build_id="build-android",
                platform="android",
                repo_dir=str(repo_dir),
                env={"GEM_HOME": "/tmp/gems", "RUBY_VERSION": "3.2.0"},
                log=logs.append,
            )

        self.assertIn(("bundle", "_2.7.2_", "install"), runner.calls)
        self.assertTrue(any("Using compatible installed Ruby 3.3.9 for RUBY_VERSION requirement 3.2.0+" in line for line in logs))

    def test_prepare_android_toolchain_fails_when_lockfile_requires_newer_ruby(self) -> None:
        runner = FakeCommandRunner()
        executor = SetupExecutor(runner)

        runner.add_response(["rbenv", "versions", "--bare"], stdout="3.1.0\n3.2.0\n")
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
                    repo_dir=str(repo_dir),
                    env={"GEM_HOME": "/tmp/gems"},
                    log=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
