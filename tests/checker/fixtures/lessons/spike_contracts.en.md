# Fixture: contracts and refusals

Technical fixture of the checker prototype. This is not a course lesson.

The program reads counts and refuses invalid input explicitly.

<!-- run: contracts_demo -->

```cpp
#include <iostream>
#include <string>

#include "parse_count.hpp"

int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        int count{0};
        const ParseStatus status{parse_count(line, count)};
        if (status == ParseStatus::ok) {
            std::cout << "accepted: " << count << "\n";
        } else {
            std::cout << "refused: " << describe(status) << "\n";
        }
    }
}
```

The header and the definitions come from shared files (`source=`).

<!-- file: contracts_demo parse_count.hpp source=tests/checker/fixtures/shared/parse_count.hpp -->

```cpp
#pragma once

#include <string>

enum class ParseStatus { ok, empty, not_a_number, negative };

// Every text is accepted as input and classified; there is no precondition.
// On ParseStatus::ok, count receives the value; otherwise count is unchanged.
ParseStatus parse_count(const std::string& text, int& count);

std::string describe(ParseStatus status);
```

<!-- file: contracts_demo parse_count.cpp source=tests/checker/fixtures/shared/parse_count.cpp -->

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

First run: a valid count and text after a number.

<!-- input: contracts_demo -->

```text
5
12abc
```

<!-- output: contracts_demo -->

```text
accepted: 5
refused: not a whole number
```

Second run: an empty line, a negative number, a valid count.

<!-- input: contracts_demo -->

```text

-3
40
```

<!-- output: contracts_demo -->

```text
refused: empty input
refused: negative count
accepted: 40
```

The check program covers every branch and that a refusal leaves the result unchanged.

<!-- test: contracts_checks -->

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

<!-- file: contracts_checks parse_count.hpp source=tests/checker/fixtures/shared/parse_count.hpp -->

```cpp
#pragma once

#include <string>

enum class ParseStatus { ok, empty, not_a_number, negative };

// Every text is accepted as input and classified; there is no precondition.
// On ParseStatus::ok, count receives the value; otherwise count is unchanged.
ParseStatus parse_count(const std::string& text, int& count);

std::string describe(ParseStatus status);
```

<!-- file: contracts_checks parse_count.cpp source=tests/checker/fixtures/shared/parse_count.cpp -->

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
