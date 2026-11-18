#include <iostream>
#include <string>

#include "inventory/inventory.hpp"

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
    using inventory::AddResult;
    inventory::Inventory shelf{5};
    check(shelf.count() == 0 && shelf.capacity() == 5, "a new inventory is empty");
    check(shelf.add(5) == AddResult::accepted && shelf.count() == 5, "filling up to the capacity is accepted");
    check(shelf.add(1) == AddResult::over_capacity && shelf.count() == 5, "going over the capacity is refused, count unchanged");
    check(shelf.add(-2) == AddResult::invalid_amount && shelf.count() == 5, "a negative amount is refused, count unchanged");
    inventory::Inventory none{0};
    check(none.add(1) == AddResult::over_capacity && none.count() == 0, "a zero capacity accepts nothing");
    std::cout << (failed == 0 ? "all checks passed\n" : "some checks failed\n");
    return failed == 0 ? 0 : 1;
}
