"""Marker syntax and the rules between markers (no compiler needed)."""

from tests.checker.helpers import CheckerTest, code, pair

MAIN = "int main() {\n    return 0;\n}\n"


class MarkerTests(CheckerTest):
    def lint_text(self, text: str):
        return self.lint(self.make_repo(pair("course/lesson", text)))

    def test_every_kind_is_accepted(self):
        text = "\n".join([
            "# Lesson", "",
            code("<!-- run: demo exit=0 -->", MAIN),
            code("<!-- file: demo helper.hpp -->", "#pragma once\n"),
            code("<!-- input: demo -->", "1\n", "text"),
            code("<!-- output: demo -->", "", "text"),
            code("<!-- compile: builds -->", MAIN),
            code("<!-- test: checks -->", MAIN),
            code("<!-- compile_fail: broken at=2:5 error=undeclared identifier -->", MAIN),
            code("<!-- compile_unsafe: unsafe allow=-Wreturn-stack-address@3,-Wdangling-gsl@5 -->", MAIN),
            code("<!-- fragment -->", "int x{1};\n"),
        ])
        result = self.lint_text(text)
        self.assertClean(result)
        self.assertEqual(result.summary["programs"], 5)
        self.assertEqual(result.summary["fragments"], 1)

    def test_unknown_kind_above_a_code_block(self):
        self.assertProtocol(self.lint_text(code("<!-- static_unsafe: demo -->", MAIN)), "unknown_kind")

    def test_ordinary_comment_stays_text(self):
        text = "<!-- TODO: explain the output -->\n\n```text\nany text\n```\n"
        self.assertClean(self.lint_text(text))

    def test_reserved_kinds_are_not_implemented(self):
        for kind in ("diagnostic", "concurrent", "benchmark"):
            with self.subTest(kind=kind):
                self.assertProtocol(self.lint_text(code(f"<!-- {kind}: demo -->", MAIN)), "reserved_kind")

    def test_lookalike_markers_are_refused(self):
        for line in ("<!--run: demo-->", "  <!-- run: demo -->", "<!-- runs: demo -->",
                     "<!-- Output: demo -->", "<!-- fragment-->"):
            with self.subTest(line=line):
                self.assertProtocol(self.lint_text(code(line, MAIN)), "malformed_marker")

    def test_unmarked_cpp_block(self):
        self.assertProtocol(self.lint_text("```cpp\n" + MAIN + "```\n"), "unmarked_block")

    def test_indented_cpp_block(self):
        self.assertProtocol(self.lint_text("- item\n\n    ```cpp\n    int x{1};\n    ```\n"), "indented_block")

    def test_duplicate_name(self):
        text = code("<!-- compile: demo -->", MAIN) + "\n" + code("<!-- compile_unsafe: demo -->", MAIN)
        self.assertProtocol(self.lint_text(text), "duplicate_name")

    def test_run_needs_an_output_block(self):
        self.assertProtocol(self.lint_text(code("<!-- run: demo -->", MAIN)), "missing_output")

    def test_output_without_a_program(self):
        self.assertProtocol(self.lint_text(code("<!-- output: nobody -->", "x\n", "text")), "orphan_block")

    def test_input_without_an_output(self):
        text = code("<!-- run: demo -->", MAIN) + code("<!-- output: demo -->", "", "text") \
            + code("<!-- input: demo -->", "1\n", "text")
        self.assertProtocol(self.lint_text(text), "missing_output")

    def test_attribute_rules(self):
        cases = {
            "<!-- run: demo colour=red -->": "bad_attribute",
            "<!-- run: demo source=course/x.cpp exit=1 -->": "bad_attribute",
            "<!-- run: demo exit=256 -->": "bad_attribute",
            "<!-- run: Demo -->": "bad_name",
            "<!-- compile_fail: demo error=x -->": "bad_attribute",
            "<!-- compile_fail: demo at=2 error=( -->": "bad_attribute",
            "<!-- compile_unsafe: demo allow=-Wfoo -->": "bad_attribute",
            "<!-- compile_unsafe: demo allow=-Wfoo@3,-Wfoo@3 -->": "bad_attribute",
        }
        for marker, category in cases.items():
            with self.subTest(marker=marker):
                self.assertProtocol(self.lint_text(code(marker, MAIN)), category)

    def test_marker_must_be_directly_above_its_block(self):
        self.assertProtocol(self.lint_text("<!-- compile: demo -->\n\nSome text.\n\n```cpp\n" + MAIN + "```\n"),
                            "marker_without_block")

    def test_block_language_must_match(self):
        text = code("<!-- run: demo -->", MAIN) + code("<!-- output: demo -->", "x\n", "cpp")
        self.assertProtocol(self.lint_text(text), "wrong_block_language")

    def test_unclosed_block(self):
        self.assertProtocol(self.lint_text("<!-- compile: demo -->\n\n```cpp\nint main() {}\n"), "unclosed_block")

    def test_marked_blocks_are_ascii(self):
        self.assertProtocol(self.lint_text(code("<!-- compile: demo -->", "// zażółć\n" + MAIN)), "non_ascii")

    def test_output_block_for_unsafe_code_is_a_mode_conflict(self):
        text = code("<!-- compile_unsafe: demo -->", MAIN) + code("<!-- output: demo -->", "", "text")
        self.assertProtocol(self.lint_text(text), "mode_conflict")

    def test_output_block_for_a_test_program_is_a_mode_conflict(self):
        text = code("<!-- test: demo -->", MAIN) + code("<!-- output: demo -->", "", "text")
        self.assertProtocol(self.lint_text(text), "mode_conflict")

    def test_file_blocks_of_markdown_programs(self):
        cases = {
            code("<!-- compile: demo -->", MAIN) + code("<!-- file: demo main.cpp -->", MAIN): "bad_path",
            code("<!-- compile: demo -->", MAIN) + code("<!-- file: demo sub/x.hpp -->", "\n"): "bad_path",
            code("<!-- file: nobody x.hpp -->", "\n"): "orphan_block",
            code("<!-- compile: demo -->", MAIN) + code("<!-- file: demo x.hpp -->", "\n")
            + code("<!-- file: demo x.hpp -->", "\n"): "duplicate_file",
        }
        for text, category in cases.items():
            with self.subTest(category=category):
                self.assertProtocol(self.lint_text(text), category)

    def test_unknown_project_mode(self):
        self.assertProtocol(self.lint_text("<!-- project: demo dir=projects/p mode=debug -->\n"), "unknown_mode")
