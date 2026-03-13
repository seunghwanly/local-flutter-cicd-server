from __future__ import annotations

import unittest

from src.application.build_status_presenter import BuildStatusPresenter
from src.domain import BuildJob, BuildRequestData


class BuildStatusPresenterTests(unittest.TestCase):
    def test_detail_includes_stage_timeline_without_setup_process(self) -> None:
        request = BuildRequestData(flavor="dev", platform="ios")
        job = BuildJob.create(
            build_id="build-1",
            request=request,
            branch_name="develop",
            queue_key="dev-develop",
        )
        job.mark_stage_completed("request_validated", "validated")
        job.mark_stage_completed("environment_prepared", "ready")

        detail = BuildStatusPresenter().detail(job, "/tmp/build.log")

        self.assertNotIn("setup", detail["processes"])
        self.assertTrue(any(stage["name"] == "request_validated" for stage in detail["stages"]))
        self.assertEqual("/tmp/build.log", detail["log_file_path"])
        self.assertEqual("manual", detail["trigger_source"])
        self.assertIsNone(detail["trigger_event_id"])


if __name__ == "__main__":
    unittest.main()
