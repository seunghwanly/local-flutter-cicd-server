from __future__ import annotations

import tempfile
import unittest

from src.infrastructure.command_runner import CommandRunner


class CommandRunnerTests(unittest.TestCase):
    def test_start_supports_default_buffering_without_text_conflict(self) -> None:
        runner = CommandRunner()

        with tempfile.TemporaryDirectory() as tmp:
            process = runner.start(
                ["/bin/echo", "hello"],
                env={},
                cwd=tmp,
            )
            output = list(runner.iter_lines(process))
            return_code = runner.wait(process)
            if process.stdout is not None:
                process.stdout.close()

        self.assertEqual(0, return_code)
        self.assertEqual(["hello"], output)


if __name__ == "__main__":
    unittest.main()
