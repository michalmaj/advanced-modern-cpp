#pragma once

#include <string>

namespace readings {

struct Summary {
    bool opened{false};
    int count{0};
    int total{0};
};

// Reads one whole number per line from the file NAME in the working folder.
// Empty lines are skipped and a trailing '\r' (a Windows line end) is ignored.
Summary summarize_file(const std::string& name);

}  // namespace readings
