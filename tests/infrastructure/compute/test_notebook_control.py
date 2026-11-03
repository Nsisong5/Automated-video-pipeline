import unittest
from unittest.mock import patch, MagicMock
from infrastructure.compute.kaggle.notebook_control import (
    classify_kaggle_output, KaggleErrorCategory, push_job_request, start_notebook, KaggleCommandError, CommandResult
)

class TestNotebookControlClassification(unittest.TestCase):
    def test_classify_auth_or_permission(self):
        cat, msg = classify_kaggle_output(1, "", "401 Client Error: Unauthorized for url: https://api.kaggle.com/v1/datasets.DatasetApiService/GetDatasetStatus", ["kaggle", "datasets", "status"])
        self.assertEqual(cat, KaggleErrorCategory.AUTH_OR_PERMISSION)

        cat, msg = classify_kaggle_output(1, "", "403 Client Error: Forbidden for url: https://api.kaggle.com/v1/kernels.KernelsApiService/GetKernel", ["kaggle", "kernels", "pull"])
        self.assertEqual(cat, KaggleErrorCategory.AUTH_OR_PERMISSION)

    def test_classify_network_unreachable(self):
        cat, msg = classify_kaggle_output(1, "", "Temporary failure in name resolution", ["kaggle", "kernels", "push"])
        self.assertEqual(cat, KaggleErrorCategory.NETWORK_UNREACHABLE)

    def test_classify_transient_api(self):
        cat, msg = classify_kaggle_output(1, "Expecting value: line 1 column 1 (char 0)", "", ["kaggle", "kernels", "push"])
        self.assertEqual(cat, KaggleErrorCategory.TRANSIENT_API)

    def test_classify_success(self):
        cat, msg = classify_kaggle_output(0, "ready", "", ["kaggle", "datasets", "status"])
        self.assertEqual(cat, KaggleErrorCategory.SUCCESS)


class TestPushJobRequestDatasetVerification(unittest.TestCase):
    @patch("infrastructure.compute.kaggle.notebook_control._run")
    @patch("os.path.getsize", return_value=1234)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=unittest.mock.mock_open())
    def test_push_job_request_success_when_ready(self, mock_open, mock_makedirs, mock_getsize, mock_run):
        mock_run.side_effect = [
            CommandResult(0, "ready", "", [], KaggleErrorCategory.SUCCESS),
            CommandResult(0, "Dataset version created", "", [], KaggleErrorCategory.SUCCESS),
            CommandResult(0, "ready", "", [], KaggleErrorCategory.SUCCESS),
        ]

        push_job_request("testuser", [{"prompt": "test"}])
        self.assertGreaterEqual(mock_run.call_count, 3)

    @patch("infrastructure.compute.kaggle.notebook_control._run")
    @patch("os.path.getsize", return_value=1234)
    @patch("os.makedirs")
    @patch("builtins.open", new_callable=unittest.mock.mock_open())
    def test_push_job_request_raises_on_auth_error(self, mock_open, mock_makedirs, mock_getsize, mock_run):
        mock_run.side_effect = KaggleCommandError(
            KaggleErrorCategory.AUTH_OR_PERMISSION,
            "Unauthorized",
            ["kaggle", "datasets", "status"],
            1,
            "401 Unauthorized"
        )

        with self.assertRaises(KaggleCommandError):
            push_job_request("testuser", [{"prompt": "test"}])


class TestStartNotebookTriggerVerification(unittest.TestCase):
    @patch("infrastructure.compute.kaggle.notebook_control.get_status")
    @patch("infrastructure.compute.kaggle.notebook_control._run")
    @patch("os.path.exists", return_value=True)
    @patch("os.makedirs")
    @patch("json.load")
    @patch("builtins.open", new_callable=unittest.mock.mock_open())
    def test_start_notebook_success_with_transient_quirk(self, mock_open, mock_json_load, mock_makedirs, mock_exists, mock_run, mock_get_status):
        mock_json_load.return_value = {
            "id": "testuser/ltx-video",
            "code_file": "notebook.ipynb"
        }
        # pull -> push (returns Expecting value transient error) -> get_status (initial vs running)
        mock_run.side_effect = [
            CommandResult(0, "pulled", "", [], KaggleErrorCategory.SUCCESS), # pull
            CommandResult(1, "", "Expecting value: line 1 column 1 (char 0)", [], KaggleErrorCategory.TRANSIENT_API), # push
        ]
        mock_get_status.side_effect = [
            "complete",   # initial before push
            "running",    # polled after push
        ]

        start_notebook("testuser")
        self.assertTrue(mock_run.called)


if __name__ == '__main__':
    unittest.main()
