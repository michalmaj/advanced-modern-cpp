#include "inventory/inventory.hpp"

#include <cassert>

namespace inventory {

Inventory::Inventory(int capacity) : capacity_{capacity} {
    assert(capacity >= 0);
}

AddResult Inventory::add(int amount) {
    if (amount <= 0) {
        return AddResult::invalid_amount;
    }
    if (amount > capacity_ - count_) {
        return AddResult::over_capacity;
    }
    count_ += amount;
    return AddResult::accepted;
}

int Inventory::count() const {
    return count_;
}

int Inventory::capacity() const {
    return capacity_;
}

}  // namespace inventory
