#include <iostream>
#include <string>

#include "readings/readings.hpp"

int main() {
    std::string name;
    while (std::getline(std::cin, name)) {
        const readings::Summary summary{readings::summarize_file(name)};
        if (!summary.opened) {
            std::cout << name << ": cannot open\n";
        } else {
            std::cout << name << ": " << summary.count << " value(s), total " << summary.total << "\n";
        }
    }
}
