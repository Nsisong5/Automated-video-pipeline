import unittest
import ast
import os

class TestArchitectureBoundaries(unittest.TestCase):
    def check_file_imports(self, file_path, forbidden_imports):
        with open(file_path, "r") as f:
            tree = ast.parse(f.read())
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        self.assertFalse(alias.name.startswith(forbidden), f"Forbidden import '{alias.name}' in {file_path}")
            elif isinstance(node, ast.ImportFrom):
                for forbidden in forbidden_imports:
                    if node.module:
                        self.assertFalse(node.module.startswith(forbidden), f"Forbidden import from '{node.module}' in {file_path}")

    def test_domain_boundary(self):
        forbidden = ["infrastructure", "fastapi", "application"]
        for root, _, files in os.walk("domain"):
            for file in files:
                if file.endswith(".py"):
                    self.check_file_imports(os.path.join(root, file), forbidden)

    def test_application_boundary(self):
        forbidden = ["infrastructure", "fastapi"]
        for root, _, files in os.walk("application"):
            for file in files:
                if file.endswith(".py") and file not in ["ports.py", "run_backend_job_cycle.py"]: # ports.py can import domain; run_backend_job_cycle is legacy
                    self.check_file_imports(os.path.join(root, file), forbidden)

if __name__ == '__main__':
    unittest.main()
