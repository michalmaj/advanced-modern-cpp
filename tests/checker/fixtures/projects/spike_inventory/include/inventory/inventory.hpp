#pragma once

namespace inventory {

enum class AddResult { accepted, over_capacity, invalid_amount };

// Keeps 0 <= count() <= capacity().
class Inventory {
public:
    // Precondition: capacity >= 0 (checked with assert in debug builds).
    explicit Inventory(int capacity);

    // A refused amount leaves the inventory unchanged.
    AddResult add(int amount);
    int count() const;
    int capacity() const;

private:
    int capacity_;
    int count_{0};
};

}  // namespace inventory
