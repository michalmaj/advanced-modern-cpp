# Fixture: unique_ptr and ownership

Technical fixture of the checker prototype. This is not a course lesson.

The check program tests only guaranteed properties of a move.

<!-- test: ownership_checks -->

```cpp
#include <iostream>
#include <memory>
#include <string>
#include <utility>

struct Sensor {
    int id{0};
};

std::unique_ptr<Sensor> make_sensor(int id) {
    auto sensor = std::make_unique<Sensor>();
    sensor->id = id;
    return sensor;
}

int take(std::unique_ptr<Sensor> owner) {
    return owner->id;
}

int failed{0};

void check(bool condition, const std::string& name) {
    std::cout << (condition ? "PASS " : "FAIL ") << name << "\n";
    if (!condition) {
        ++failed;
    }
}

int main() {
    auto first = make_sensor(7);
    check(first != nullptr && first->id == 7, "a factory returns the owner");
    auto second = std::move(first);
    check(first == nullptr, "a moved-from unique_ptr is null");
    check(second != nullptr && second->id == 7, "the new owner holds the object");
    check(take(std::move(second)) == 7, "ownership passes into a function");
    check(second == nullptr, "the caller no longer owns the object");
    check(take(make_sensor(3)) == 3, "a temporary owner needs no std::move");
    std::cout << (failed == 0 ? "all checks passed\n" : "some checks failed\n");
    return failed == 0 ? 0 : 1;
}
```

The order of the messages follows the end of the owners' lifetimes.

<!-- run: ownership_trace -->

```cpp
#include <iostream>
#include <memory>
#include <utility>

struct Probe {
    explicit Probe(int value) : id{value} {
        std::cout << "acquire " << id << "\n";
    }
    ~Probe() {
        std::cout << "release " << id << "\n";
    }
    Probe(const Probe&) = delete;
    Probe& operator=(const Probe&) = delete;

    int id;
};

void consume(std::unique_ptr<Probe> owner) {
    std::cout << "consume " << owner->id << "\n";
}

int main() {
    auto first = std::make_unique<Probe>(1);
    auto second = std::make_unique<Probe>(2);
    consume(std::move(first));
    std::cout << "end of main\n";
}
```

<!-- output: ownership_trace -->

```text
acquire 1
acquire 2
consume 1
release 1
end of main
release 2
```

Copying the owner is rejected; the wording depends on the library, so the pattern is short.

<!-- compile_fail: copy_owner at=5:10 error=deleted -->

```cpp
#include <memory>

int main() {
    auto owner = std::make_unique<int>(5);
    auto copy = owner;
    return *copy;
}
```
