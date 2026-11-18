# Fixture: projekt katalogowy

Techniczny fixture prototypu checkera. To nie jest lekcja kursu. Projekt CMake bez CTest.

Program z projektu, uruchomiony i porównany z wynikiem.

<!-- project: inventory_demo dir=tests/checker/fixtures/projects/spike_inventory mode=run target=inventory_app -->

<!-- output: inventory_demo -->

```text
add 4: accepted
add 5: accepted
add 3: refused: over capacity
add 0: refused: invalid amount
add 1: accepted
count 10 of 10
```

Program kontrolny projektu.

<!-- project: inventory_checks dir=tests/checker/fixtures/projects/spike_inventory mode=test target=inventory_checks -->

Cały projekt musi się zbudować.

<!-- project: inventory_build dir=tests/checker/fixtures/projects/spike_inventory mode=compile -->

Plik pokazany w lekcji jest porównywany z plikiem projektu.

<!-- file: inventory_demo include/inventory/inventory.hpp -->

```cpp
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
```
