#pragma once

#include <string>

enum class ParseStatus { ok, empty, not_a_number, negative };

// Every text is accepted as input and classified; there is no precondition.
// On ParseStatus::ok, count receives the value; otherwise count is unchanged.
ParseStatus parse_count(const std::string& text, int& count);

std::string describe(ParseStatus status);
