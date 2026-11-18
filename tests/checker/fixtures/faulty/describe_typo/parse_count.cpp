// Deliberately faulty: a refusal is described with the wrong text.
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
        return "empty line";
    case ParseStatus::not_a_number:
        return "not a whole number";
    case ParseStatus::negative:
        return "negative count";
    }
    return "unknown status";
}
