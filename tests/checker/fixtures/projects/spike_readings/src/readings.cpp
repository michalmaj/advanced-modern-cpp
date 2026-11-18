#include "readings/readings.hpp"

#include <fstream>
#include <sstream>

namespace readings {

Summary summarize_file(const std::string& name) {
    Summary summary;
    std::ifstream file{name};
    if (!file) {
        return summary;
    }
    summary.opened = true;
    std::string line;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.empty()) {
            continue;
        }
        std::istringstream stream{line};
        int value{0};
        if (stream >> value) {
            summary.total += value;
            ++summary.count;
        }
    }
    return summary;
}

}  // namespace readings
