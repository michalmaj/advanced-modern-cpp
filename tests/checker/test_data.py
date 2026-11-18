"""in= (standard input from a file) and data= (data folders for runs)."""

import os
from pathlib import Path

from tests.checker.helpers import CheckerTest, code, pair
from tools.checker.datafiles import MAX_DATA_FILES, run_input
from tools.checker.execute import Settings
from tools.checker.model import Run, Status

SUM = ("#include <iostream>\n\nint main() {\n    int total{0};\n    int value{0};\n"
       "    while (std::cin >> value) {\n        total += value;\n    }\n"
       '    std::cout << total << "\\n";\n}\n')
READ = ('#include <fstream>\n#include <iostream>\n#include <string>\n\nint main() {\n'
        '    std::string name;\n    while (std::getline(std::cin, name)) {\n'
        '        std::ifstream file{name};\n        std::string first;\n'
        '        if (!file) {\n            std::cout << name << ": missing\\n";\n'
        '        } else if (!std::getline(file, first)) {\n            std::cout << name << ": empty\\n";\n'
        '        } else {\n            if (!first.empty() && first.back() == \'\\r\') {\n'
        '                first.pop_back();\n            }\n'
        '            std::cout << name << ": " << first << "\\n";\n        }\n    }\n}\n')
APPEND = ('#include <fstream>\n#include <iostream>\n#include <string>\n\nint main() {\n'
          '    std::string path;\n    std::getline(std::cin, path);\n'
          '    std::ofstream out{path, std::ios::app};\n    out << "changed\\n";\n'
          '    std::cout << "done\\n";\n}\n')


def run_with_input(marker_attrs: str, expected: str) -> str:
    return code("<!-- run: sum -->", SUM) + code(f"<!-- output: sum{marker_attrs} -->", expected, "text")


class InputFileProtocolTests(CheckerTest):
    def lint_files(self, lesson: str, extra: dict):
        return self.lint(self.make_repo({**pair("course/lesson", lesson), **extra}))

    def test_valid_input_file(self):
        self.assertClean(self.lint_files(run_with_input(" in=support/data/numbers.txt", "6\n"),
                                         {"support/data/numbers.txt": "1 2 3\n"}))

    def test_input_file_paths(self):
        cases = {
            " in=support/data/missing.txt": "missing_file",
            " in=support/../outside.txt": "path_escape",
            " in=other/numbers.txt": "path_not_allowed",
            " in=/etc/passwd": "bad_path",
            " in=support/data": "missing_file",
        }
        for attrs, category in cases.items():
            with self.subTest(attrs=attrs):
                result = self.lint_files(run_with_input(attrs, "6\n"),
                                         {"other/numbers.txt": "1\n", "support/data/x.txt": "1\n"})
                self.assertProtocol(result, category)

    def test_input_file_through_a_symbolic_link(self):
        root = self.make_repo({**pair("course/lesson", run_with_input(" in=support/link.txt", "6\n")),
                               "support/real.txt": "1 2 3\n"})
        try:
            os.symlink(root / "support" / "real.txt", root / "support" / "link.txt")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create symbolic links here: {exc}")
        self.assertProtocol(self.lint(root), "symlink")

    def test_input_block_and_input_file_together(self):
        lesson = (code("<!-- run: sum -->", SUM) + code("<!-- input: sum -->", "1\n", "text")
                  + code("<!-- output: sum in=support/n.txt -->", "1\n", "text"))
        self.assertProtocol(self.lint_files(lesson, {"support/n.txt": "1\n"}), "input_conflict")

    def test_input_file_cannot_make_unsafe_code_run(self):
        lesson = (code("<!-- compile_unsafe: risky -->", "int main() {\n    return 0;\n}\n")
                  + code("<!-- output: risky in=support/n.txt -->", "", "text"))
        self.assertProtocol(self.lint_files(lesson, {"support/n.txt": "1\n"}), "mode_conflict")

    def test_input_file_bytes_are_passed_unchanged(self):
        root = self.make_repo({"support/crlf.txt": b"1\r\n2\r\n"})
        run = Run(1, None, "", 1, "support/crlf.txt", root / "support" / "crlf.txt")
        self.assertEqual(run_input(run), b"1\r\n2\r\n")
        self.assertEqual(run_input(Run(1, "1\n", "", 1)), b"1\n")


class DataFolderProtocolTests(CheckerTest):
    def lint_files(self, lesson: str, extra: dict):
        return self.lint(self.make_repo({**pair("course/lesson", lesson), **extra}))

    def reader(self, data: str) -> str:
        return code(f"<!-- run: reader data={data} -->", READ) + code("<!-- output: reader -->", "", "text")

    def test_valid_data_folder(self):
        self.assertClean(self.lint_files(self.reader("support/data"), {"support/data/a.txt": "x\n"}))

    def test_data_folder_paths(self):
        cases = {
            "support/none": "missing_file",
            "support/data/a.txt": "missing_file",
            "support/../course": "path_escape",
            "other/data": "path_not_allowed",
            "support": "data_too_broad",
        }
        for data, category in cases.items():
            with self.subTest(data=data):
                result = self.lint_files(self.reader(data), {"support/data/a.txt": "x\n", "other/data/a.txt": "x\n"})
                self.assertProtocol(result, category)

    def test_symbolic_link_inside_a_data_folder(self):
        root = self.make_repo({**pair("course/lesson", self.reader("support/data")), "support/data/a.txt": "x\n"})
        try:
            os.symlink(root / "support" / "data" / "a.txt", root / "support" / "data" / "b.txt")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create symbolic links here: {exc}")
        self.assertProtocol(self.lint(root), "symlink")

    def test_too_many_data_files(self):
        files = {f"support/data/f{i}.txt": "x\n" for i in range(MAX_DATA_FILES + 1)}
        self.assertProtocol(self.lint_files(self.reader("support/data"), files), "data_too_large")

    def test_data_is_only_for_programs_that_run(self):
        for marker in ("<!-- compile: c data=support/data -->", "<!-- compile_unsafe: c data=support/data -->",
                       "<!-- compile_fail: c data=support/data at=1 error=x -->"):
            with self.subTest(marker=marker):
                result = self.lint_files(code(marker, "int main() {}\n"), {"support/data/a.txt": "x\n"})
                self.assertTrue({"bad_attribute", "bad_name"} & set(self.protocol_categories(result)), result.verdicts)

    def test_project_in_compile_mode_takes_no_data(self):
        files = {"projects/p/CMakeLists.txt": "cmake_minimum_required(VERSION 3.28)\nproject(p CXX)\n",
                 "projects/p/checker-project.json": '{"id": "p", "modes": ["compile"], "targets": []}',
                 "support/data/a.txt": "x\n"}
        self.assertProtocol(self.lint_files("<!-- project: p dir=projects/p mode=compile data=support/data -->\n",
                                            files), "bad_attribute")


class DataRunTests(CheckerTest):
    def run_files(self, lesson: str, extra: dict, work=None):
        return self.check(self.make_repo({**pair("course/lesson", lesson), **extra}), work=work)

    def test_several_input_files_and_an_inline_case(self):
        lesson = (code("<!-- run: sum -->", SUM)
                  + code("<!-- input: sum -->", "4 5\n", "text") + code("<!-- output: sum -->", "9\n", "text")
                  + code("<!-- output: sum in=support/a.txt -->", "6\n", "text")
                  + code("<!-- output: sum in=support/empty.txt -->", "0\n", "text"))
        result = self.run_files(lesson, {"support/a.txt": "1\n2\n3\n", "support/empty.txt": ""})
        self.assertClean(result)
        self.assertEqual(len([v for v in result.verdicts if "/run" in v.id]), 3)

    def test_data_folder_files_empty_and_crlf(self):
        lesson = (code("<!-- run: reader data=support/data -->", READ)
                  + code("<!-- input: reader -->", "a.txt\nempty.txt\ncrlf.txt\nnone.txt\n", "text")
                  + code("<!-- output: reader -->", "a.txt: alpha\nempty.txt: empty\ncrlf.txt: windows\nnone.txt: missing\n",
                         "text"))
        result = self.run_files(lesson, {"support/data/a.txt": "alpha\n", "support/data/empty.txt": "",
                                         "support/data/crlf.txt": b"windows\r\nsecond\r\n"})
        self.assertClean(result)

    def test_each_run_gets_a_fresh_copy_and_the_original_stays(self):
        counter = ('#include <fstream>\n#include <iostream>\n\nint main() {\n    int n{0};\n'
                   '    {\n        std::ifstream in{"n.txt"};\n        in >> n;\n    }\n'
                   '    std::ofstream{"n.txt"} << n + 1 << "\\n";\n    std::cout << n + 1 << "\\n";\n}\n')
        lesson = (code("<!-- run: counter data=support/data -->", counter)
                  + code("<!-- output: counter -->", "8\n", "text") + code("<!-- output: counter -->", "8\n", "text"))
        root = self.make_repo({**pair("course/lesson", lesson), "support/data/n.txt": "7\n"})
        self.assertClean(self.check(root))
        self.assertEqual((root / "support" / "data" / "n.txt").read_text(), "7\n")

    def test_changing_the_original_is_detected(self):
        root = self.make_repo({"support/data/victim.txt": "original\n"})
        victim = (root / "support" / "data" / "victim.txt").resolve().as_posix()
        lesson = (code("<!-- run: writer data=support/data -->", APPEND)
                  + code("<!-- input: writer -->", victim + "\n", "text")
                  + code("<!-- output: writer -->", "done\n", "text"))
        for rel, content in pair("course/lesson", lesson).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        self.one(self.check(root), "#writer/data", Status.FAIL, "source_modified")

    def test_runs_never_start_in_the_source_folder(self):
        work = self.work_dir()
        lesson = (code("<!-- run: where data=support/data -->", READ)
                  + code("<!-- input: where -->", "main.cpp\n", "text")
                  + code("<!-- output: where -->", "main.cpp: missing\n", "text"))
        self.assertClean(self.run_files(lesson, {"support/data/a.txt": "x\n"}, work=work))

    def test_test_program_with_data(self):
        checks = ('#include <fstream>\n#include <iostream>\n#include <string>\n\nint main() {\n'
                  '    std::ifstream file{"a.txt"};\n    std::string word;\n    file >> word;\n'
                  '    std::cout << (word == "alpha" ? "PASS read\\n" : "FAIL read\\n");\n'
                  '    return word == "alpha" ? 0 : 1;\n}\n')
        result = self.run_files(code("<!-- test: checks data=support/data -->", checks), {"support/data/a.txt": "alpha\n"})
        self.one(result, "#checks/test", Status.PASS)


class ProjectDataTests(CheckerTest):
    def test_project_runs_in_a_copy_of_its_data_folder(self):
        self.need_build_tools()
        cmake = ("cmake_minimum_required(VERSION 3.28)\nproject(p LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n"
                 "set(CMAKE_CXX_STANDARD_REQUIRED ON)\nadd_executable(app main.cpp)\n")
        files = {"projects/p/CMakeLists.txt": cmake, "projects/p/main.cpp": READ,
                 "projects/p/checker-project.json": '{"id": "p", "modes": ["run"], "targets": ["app"]}',
                 "projects/p/data/a.txt": "alpha\n"}
        lesson = ("<!-- project: p dir=projects/p mode=run target=app data=projects/p/data -->\n\n"
                  + code("<!-- output: p in=support/names.txt -->", "a.txt: alpha\nmain.cpp: missing\n", "text"))
        root = self.make_repo({**pair("course/lesson", lesson), **files, "support/names.txt": "a.txt\nmain.cpp\n"})
        result = self.check(root, settings=Settings(cmake=os.environ.get("CMAKE", "cmake"),
                                                    ninja=os.environ.get("NINJA", "ninja")))
        self.assertClean(result)
        self.one(result, "#p/run1", Status.PASS)
        self.assertFalse(any(Path(dirpath).name == "build" for dirpath, _, _ in os.walk(root)),
                         "nothing may be built inside the repository")
