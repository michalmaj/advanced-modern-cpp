#include <iostream>
#include <string>

#include "readings/readings.hpp"

namespace {

int failed{0};

void check(bool condition, const std::string& name) {
    std::cout << (condition ? "PASS " : "FAIL ") << name << "\n";
    if (!condition) {
        ++failed;
    }
}

}  // namespace

int main() {
    const readings::Summary plain{readings::summarize_file("readings.txt")};
    check(plain.opened && plain.count == 3 && plain.total == 15, "a file with three values");
    const readings::Summary windows{readings::summarize_file("crlf.txt")};
    check(windows.opened && windows.count == 2 && windows.total == 3, "Windows line ends are accepted");
    const readings::Summary none{readings::summarize_file("missing.txt")};
    check(!none.opened && none.count == 0, "a missing file is reported, not read");
    std::cout << (failed == 0 ? "all checks passed\n" : "some checks failed\n");
    return failed == 0 ? 0 : 1;
}
