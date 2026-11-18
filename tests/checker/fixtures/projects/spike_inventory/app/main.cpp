#include <initializer_list>
#include <iostream>

#include "inventory/inventory.hpp"

namespace {

const char* describe(inventory::AddResult result) {
    switch (result) {
    case inventory::AddResult::accepted:
        return "accepted";
    case inventory::AddResult::over_capacity:
        return "refused: over capacity";
    case inventory::AddResult::invalid_amount:
        return "refused: invalid amount";
    }
    return "unknown result";
}

}  // namespace

int main() {
    inventory::Inventory shelf{10};
    for (int amount : {4, 5, 3, 0, 1}) {
        std::cout << "add " << amount << ": " << describe(shelf.add(amount)) << "\n";
    }
    std::cout << "count " << shelf.count() << " of " << shelf.capacity() << "\n";
}
