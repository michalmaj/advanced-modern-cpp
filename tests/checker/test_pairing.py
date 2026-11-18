"""Polish / English pairs (no compiler needed)."""

from tests.checker.helpers import CheckerTest, code

MAIN = "int main() {\n    return 0;\n}\n"
LESSON = "# Lekcja\n\n" + code("<!-- compile: demo -->", MAIN) + "\n" + code("<!-- compile: second -->", MAIN)
LESSON_EN = "# Lesson\n\nDifferent prose.\n\n" + code("<!-- compile: demo -->", MAIN) + "\n" \
    + code("<!-- compile: second -->", MAIN)


class PairingTests(CheckerTest):
    def lint_files(self, files: dict):
        return self.lint(self.make_repo(files))

    def test_matching_pair_with_different_prose(self):
        self.assertClean(self.lint_files({"course/a.md": LESSON, "course/a.en.md": LESSON_EN}))

    def test_missing_english_lesson(self):
        self.assertProtocol(self.lint_files({"course/a.md": LESSON}), "pairing_missing")

    def test_missing_polish_lesson(self):
        self.assertProtocol(self.lint_files({"course/a.en.md": LESSON_EN}), "pairing_missing")

    def test_code_difference(self):
        changed = LESSON_EN.replace("return 0;", "return 1;", 1)
        self.assertProtocol(self.lint_files({"course/a.md": LESSON, "course/a.en.md": changed}), "pairing_mismatch")

    def test_marker_difference(self):
        changed = LESSON_EN.replace("<!-- compile: second -->", "<!-- test: second -->")
        self.assertProtocol(self.lint_files({"course/a.md": LESSON, "course/a.en.md": changed}), "pairing_mismatch")

    def test_order_difference(self):
        swapped = "# Lesson\n\n" + code("<!-- compile: second -->", MAIN) + "\n" + code("<!-- compile: demo -->", MAIN)
        self.assertProtocol(self.lint_files({"course/a.md": LESSON, "course/a.en.md": swapped}), "pairing_mismatch")

    def test_extra_block(self):
        extra = LESSON_EN + "\n" + code("<!-- compile: third -->", MAIN)
        self.assertProtocol(self.lint_files({"course/a.md": LESSON, "course/a.en.md": extra}), "pairing_mismatch")

    def test_windows_line_ends_are_normalised(self):
        crlf = LESSON_EN.replace("\n", "\r\n").encode("utf-8")
        result = self.lint_files({"course/a.md": LESSON, "course/a.en.md": crlf})
        self.assertClean(result)
        self.assertEqual(result.environment["lesson_line_ends"], "crlf")

    def test_normalisation_does_not_hide_a_real_difference(self):
        crlf = LESSON_EN.replace("return 0;", "return 2;", 1).replace("\n", "\r\n").encode("utf-8")
        self.assertProtocol(self.lint_files({"course/a.md": LESSON, "course/a.en.md": crlf}), "pairing_mismatch")

    def test_mismatching_pair_is_not_built(self):
        changed = LESSON_EN.replace("return 0;", "return 1;", 1)
        result = self.lint_files({"course/a.md": LESSON, "course/a.en.md": changed})
        self.assertEqual(result.summary["lesson_pairs_checked"], 0)
        self.assertEqual(result.summary["lessons_blocked_by_protocol_errors"], 1)


class NewAttributePairingTests(CheckerTest):
    """in=, data= and against= are part of the marker line, so PL and EN must agree on them."""

    FILES = {"support/a.txt": "1\n", "support/b.txt": "2\n", "support/d1/x.txt": "x\n", "support/d2/x.txt": "y\n",
             "support/f1/h.cpp": "int h() {\n    return 1;\n}\n", "support/f2/h.cpp": "int h() {\n    return 2;\n}\n"}

    def lesson(self, first="support/a.txt", second="support/b.txt", data="support/d1", against="support/f1/h.cpp"):
        program = "int main() {\n    return 0;\n}\n"
        return (code(f"<!-- run: demo data={data} -->", program)
                + code(f"<!-- output: demo in={first} -->", "", "text")
                + code(f"<!-- output: demo in={second} -->", "", "text")
                + code(f"<!-- test: checks against={against} -->", program)
                + code("<!-- file: checks h.cpp -->", "int h() {\n    return 0;\n}\n"))

    def test_matching_new_attributes_pass(self):
        self.assertClean(self.lint(self.make_repo({"course/a.md": self.lesson(), "course/a.en.md": self.lesson(),
                                                   **self.FILES})))

    def test_differences_in_new_attributes(self):
        variants = {
            "in=": self.lesson(first="support/b.txt", second="support/b.txt"),
            "order of cases": self.lesson(first="support/b.txt", second="support/a.txt"),
            "data=": self.lesson(data="support/d2"),
            "against=": self.lesson(against="support/f2/h.cpp"),
        }
        for name, english in variants.items():
            with self.subTest(difference=name):
                result = self.lint(self.make_repo({"course/a.md": self.lesson(), "course/a.en.md": english,
                                                   **self.FILES}))
                self.assertProtocol(result, "pairing_mismatch")

    def test_crlf_lesson_with_new_attributes(self):
        crlf = self.lesson().replace("\n", "\r\n").encode("utf-8")
        self.assertClean(self.lint(self.make_repo({"course/a.md": self.lesson(), "course/a.en.md": crlf,
                                                   **self.FILES})))
