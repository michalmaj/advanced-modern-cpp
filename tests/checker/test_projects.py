"""Directory projects built with CMake and Ninja (needs clang++, CMake 3.28+, Ninja)."""

import json
import os

from tests.checker.helpers import CheckerTest, code, pair
from tools.checker.execute import Settings
from tools.checker.model import Status

APP = '#include <iostream>\n\n#include "greet.hpp"\n\nint main() {\n    std::cout << greeting() << "\\n";\n}\n'
CHECKS = ('#include "greet.hpp"\n\nint main() {\n    return greeting() == "hello" ? 0 : 1;\n}\n')
HEADER = "#pragma once\n\n#include <string>\n\nstd::string greeting();\n"
SOURCE = '#include "greet.hpp"\n\nstd::string greeting() {\n    return "hello";\n}\n'
CMAKE = """cmake_minimum_required(VERSION 3.28)
project(greet LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_library(greet STATIC src/greet.cpp)
target_include_directories(greet PUBLIC include)
add_executable(greet_app app/main.cpp)
target_link_libraries(greet_app PRIVATE greet)
add_executable(greet_checks checks/main.cpp)
target_link_libraries(greet_checks PRIVATE greet)
"""


def project(modes=("compile", "run", "test"), source=SOURCE, app=APP):
    base = "projects/greet"
    return {
        f"{base}/checker-project.json": json.dumps({"id": "greet", "modes": list(modes),
                                                     "targets": ["greet_app", "greet_checks"]}),
        f"{base}/CMakeLists.txt": CMAKE,
        f"{base}/include/greet.hpp": HEADER,
        f"{base}/src/greet.cpp": source,
        f"{base}/app/main.cpp": app,
        f"{base}/checks/main.cpp": CHECKS,
    }


class ProjectTests(CheckerTest):
    def run_project(self, lesson: str, files: dict, work=None):
        self.need_build_tools()
        root = self.make_repo({**pair("course/lesson", lesson), **files})
        return self.check(root, work=work, settings=Settings(cmake=os.environ.get("CMAKE", "cmake"),
                                                             ninja=os.environ.get("NINJA", "ninja")))

    def test_run_test_and_compile_modes(self):
        lesson = ("<!-- project: demo dir=projects/greet mode=run target=greet_app -->\n\n"
                  + code("<!-- output: demo -->", "hello\n", "text")
                  + "\n<!-- project: checks dir=projects/greet mode=test target=greet_checks -->\n"
                  + "\n<!-- project: whole dir=projects/greet mode=compile -->\n\n"
                  + code("<!-- file: demo include/greet.hpp -->", HEADER))
        result = self.run_project(lesson, project())
        self.assertClean(result)
        for suffix in ("#demo/configure", "#demo/build", "#demo/run1", "#checks/test", "#whole/build"):
            self.one(result, suffix, Status.PASS)

    def test_failing_check_program(self):
        lesson = "<!-- project: checks dir=projects/greet mode=test target=greet_checks -->\n"
        result = self.run_project(lesson, project(source=SOURCE.replace('"hello"', '"bye"')))
        self.one(result, "#checks/test", Status.FAIL, "test_failed")

    def test_build_failure(self):
        lesson = "<!-- project: whole dir=projects/greet mode=compile -->\n"
        result = self.run_project(lesson, project(source=SOURCE.replace("return", "retrun")))
        self.one(result, "#whole/build", Status.FAIL, "build_failed")

    def test_mode_refused_by_the_manifest_is_never_built(self):
        sentinel_app = ('#include <fstream>\n\nint main() {\n'
                        '    std::ofstream trace{"SENTINEL-project-was-executed.txt"};\n}\n')
        lesson = ("<!-- project: demo dir=projects/greet mode=run target=greet_app -->\n\n"
                  + code("<!-- output: demo -->", "", "text"))
        work = self.work_dir()
        result = self.run_project(lesson, project(modes=("compile",), app=sentinel_app), work=work)
        self.assertProtocol(result, "mode_not_allowed")
        self.assertEqual(result.summary["examples_built"], 0)
        self.assertEqual(list(work.rglob("SENTINEL-*")), [])
