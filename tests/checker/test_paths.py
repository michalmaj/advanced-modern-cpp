"""Paths in markers and directory projects (no compiler needed)."""

import json
import os

from tests.checker.helpers import CheckerTest, code, pair

MAIN = "int main() {\n    return 0;\n}\n"
HEADER = "#pragma once\n"
CMAKE = "cmake_minimum_required(VERSION 3.28)\nproject(p LANGUAGES CXX)\nadd_executable(app main.cpp)\n"


def manifest(pid="p", modes=("compile", "run", "test"), targets=("app",)):
    return json.dumps({"id": pid, "modes": list(modes), "targets": list(targets)})


def source_lesson(source: str) -> str:
    return code("<!-- compile: demo -->", MAIN) + code(f"<!-- file: demo h.hpp source={source} -->", HEADER)


def project_lesson(directory="projects/p", mode="compile", extra=""):
    return f"<!-- project: demo dir={directory} mode={mode}{extra} -->\n"


def project_files(directory="projects/p", **kwargs):
    return {f"{directory}/CMakeLists.txt": CMAKE, f"{directory}/main.cpp": MAIN,
            f"{directory}/checker-project.json": manifest(**kwargs)}


class SourcePathTests(CheckerTest):
    def lint_source(self, source: str, extra: dict | None = None):
        files = pair("course/lesson", source_lesson(source))
        files.update(extra or {"support/h.hpp": HEADER})
        return self.lint(self.make_repo(files))

    def test_shared_source_for_pl_and_en(self):
        self.assertClean(self.lint_source("support/h.hpp"))

    def test_parent_segment_is_an_escape(self):
        self.assertProtocol(self.lint_source("support/../../etc/hosts"), "path_escape")

    def test_path_syntax(self):
        for source, category in {"/etc/hosts": "bad_path", "C:/Windows/x.hpp": "bad_path",
                                 "support\\h.hpp": "bad_path", "support//h.hpp": "bad_path",
                                 "support/.hidden": "bad_path"}.items():
            with self.subTest(source=source):
                self.assertProtocol(self.lint_source(source), category)

    def test_outside_the_allowed_folders(self):
        self.assertProtocol(self.lint_source("other/h.hpp", {"other/h.hpp": HEADER}), "path_not_allowed")

    def test_missing_source_file(self):
        self.assertProtocol(self.lint_source("support/missing.hpp"), "missing_file")

    def test_source_content_must_match(self):
        self.assertProtocol(self.lint_source("support/h.hpp", {"support/h.hpp": "#pragma once\n// changed\n"}),
                            "source_mismatch")

    def test_symbolic_links_are_refused(self):
        root = self.make_repo({**pair("course/lesson", source_lesson("support/link.hpp")), "support/real.hpp": HEADER})
        try:
            os.symlink(root / "support" / "real.hpp", root / "support" / "link.hpp")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create symbolic links here: {exc}")
        self.assertProtocol(self.lint(root), "symlink")

    def test_symbolic_link_leaving_the_repository(self):
        outside = self.make_repo({"secret.hpp": HEADER})
        root = self.make_repo(pair("course/lesson", source_lesson("support/secret.hpp")))
        (root / "support").mkdir()
        try:
            os.symlink(outside / "secret.hpp", root / "support" / "secret.hpp")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create symbolic links here: {exc}")
        self.assertProtocol(self.lint(root), "symlink")

    def test_lesson_path_outside_the_repository(self):
        root = self.make_repo(pair("course/lesson", code("<!-- compile: demo -->", MAIN)))
        self.assertProtocol(self.lint(root, ("../elsewhere",)), "path_escape")


class ProjectPathTests(CheckerTest):
    def lint_project(self, lesson: str, files: dict):
        return self.lint(self.make_repo({**pair("course/lesson", lesson), **files}))

    def test_valid_project(self):
        self.assertClean(self.lint_project(project_lesson(), project_files()))

    def test_missing_project_folder(self):
        self.assertProtocol(self.lint_project(project_lesson("projects/none"), {}), "missing_file")

    def test_project_without_manifest(self):
        files = project_files()
        del files["projects/p/checker-project.json"]
        self.assertProtocol(self.lint_project(project_lesson(), files), "missing_file")

    def test_project_without_cmakelists(self):
        files = project_files()
        del files["projects/p/CMakeLists.txt"]
        self.assertProtocol(self.lint_project(project_lesson(), files), "missing_file")

    def test_bad_manifest(self):
        files = project_files()
        files["projects/p/checker-project.json"] = json.dumps({"id": "p", "modes": ["run", "deploy"], "targets": []})
        self.assertProtocol(self.lint_project(project_lesson(), files), "bad_manifest")

    def test_mode_not_declared_by_the_project(self):
        lesson = project_lesson(mode="run", extra=" target=app") + "\n" + code("<!-- output: demo -->", "", "text")
        self.assertProtocol(self.lint_project(lesson, project_files(modes=("compile",))), "mode_not_allowed")

    def test_unknown_target(self):
        self.assertProtocol(self.lint_project(project_lesson(mode="test", extra=" target=other"), project_files()),
                            "unknown_target")

    def test_test_mode_needs_a_target(self):
        self.assertProtocol(self.lint_project(project_lesson(mode="test"), project_files()), "missing_target")

    def test_forbidden_cmake_commands(self):
        for command in ("include(FetchContent)", "ExternalProject_Add(x)", "execute_process(COMMAND x)",
                        "file(DOWNLOAD https://example.invalid/x x)", "include(CTest)"):
            with self.subTest(command=command):
                files = project_files()
                files["projects/p/CMakeLists.txt"] = CMAKE + command + "\n"
                self.assertProtocol(self.lint_project(project_lesson(), files), "forbidden_cmake")

    def test_symbolic_link_inside_a_project(self):
        root = self.make_repo({**pair("course/lesson", project_lesson()), **project_files()})
        try:
            os.symlink(root / "projects" / "p" / "main.cpp", root / "projects" / "p" / "alias.cpp")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"cannot create symbolic links here: {exc}")
        self.assertProtocol(self.lint(root), "symlink")

    def test_duplicate_project_id(self):
        lesson = project_lesson("projects/p") + "\n" + project_lesson("projects/q").replace("demo", "other")
        files = {**project_files("projects/p"), **project_files("projects/q")}
        self.assertProtocol(self.lint_project(lesson, files), "duplicate_id")

    def test_shown_file_must_match_the_project(self):
        lesson = project_lesson() + "\n" + code("<!-- file: demo main.cpp -->", "int main() {}\n")
        self.assertProtocol(self.lint_project(lesson, project_files()), "source_mismatch")

    def test_shown_file_cannot_leave_the_project(self):
        lesson = project_lesson() + "\n" + code("<!-- file: demo ../q/main.cpp -->", MAIN)
        self.assertProtocol(self.lint_project(lesson, project_files()), "path_escape")
