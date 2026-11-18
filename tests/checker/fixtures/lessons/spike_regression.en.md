# Fixture: does the test catch a fault

Technical fixture of the checker prototype. This is not a course lesson.

The same check program must pass with the correct implementation and reject a deliberately faulty one (`against=`).

<!-- test: contracts_regression against=tests/checker/fixtures/faulty/negative_accepted/parse_count.cpp -->

```cpp
#include <iostream>
#include <string>

#include "parse_count.hpp"

int failed{0};

void check(bool condition, const std::string& name) {
    std::cout << (condition ? "PASS " : "FAIL ") << name << "\n";
    if (!condition) {
        ++failed;
    }
}

int main() {
    int count{7};
    check(parse_count("12", count) == ParseStatus::ok && count == 12, "a whole number is accepted");
    count = 7;
    check(parse_count("", count) == ParseStatus::empty && count == 7, "empty text is refused, count unchanged");
    check(parse_count("4x", count) == ParseStatus::not_a_number && count == 7, "trailing text is refused, count unchanged");
    check(parse_count("-1", count) == ParseStatus::negative && count == 7, "a negative number is refused, count unchanged");
    check(parse_count("0", count) == ParseStatus::ok && count == 0, "zero is accepted");
    std::cout << (failed == 0 ? "all checks passed\n" : "some checks failed\n");
    return failed == 0 ? 0 : 1;
}
```

<!-- file: contracts_regression parse_count.hpp source=tests/checker/fixtures/shared/parse_count.hpp -->

```cpp
#pragma once

#include <string>

enum class ParseStatus { ok, empty, not_a_number, negative };

// Every text is accepted as input and classified; there is no precondition.
// On ParseStatus::ok, count receives the value; otherwise count is unchanged.
ParseStatus parse_count(const std::string& text, int& count);

std::string describe(ParseStatus status);
```

<!-- file: contracts_regression parse_count.cpp source=tests/checker/fixtures/shared/parse_count.cpp -->

```cpp
#include "parse_count.hpp"

#include <sstream>

ParseStatus parse_count(const std::string& text, int& count) {
    if (text.empty()) {
        return ParseStatus::empty;
    }
    std::istringstream stream{text};
    int value{0};
    char rest{};
    if (!(stream >> value) || (stream >> rest)) {
        return ParseStatus::not_a_number;
    }
    if (value < 0) {
        return ParseStatus::negative;
    }
    count = value;
    return ParseStatus::ok;
}

std::string describe(ParseStatus status) {
    switch (status) {
    case ParseStatus::ok:
        return "accepted";
    case ParseStatus::empty:
        return "empty input";
    case ParseStatus::not_a_number:
        return "not a whole number";
    case ParseStatus::negative:
        return "negative count";
    }
    return "unknown status";
}
```
