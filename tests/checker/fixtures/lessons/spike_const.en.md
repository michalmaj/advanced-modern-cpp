# Fixture: const and pointers

Technical fixture of the checker prototype. This is not a course lesson.

The allowed operations compile.

<!-- compile: const_rules -->

```cpp
#include <iostream>

int main() {
    int value{1};
    int other{2};

    const int* reader{&value};
    reader = &other;

    int* const writer{&value};
    *writer = 3;

    std::cout << *reader << " " << value << "\n";
}
```

Writing through a pointer to const is an error.

<!-- compile_fail: write_through_reader at=4:13 error=not assignable -->

```cpp
int main() {
    int value{1};
    const int* reader{&value};
    *reader = 2;
    return value;
}
```

A const pointer cannot be pointed elsewhere.

<!-- compile_fail: move_fixed_pointer at=5:11 error=const-qualified type -->

```cpp
int main() {
    int first{1};
    int second{2};
    int* const fixed{&first};
    fixed = &second;
    return *fixed;
}
```

The declaration alone, not a program:

<!-- fragment -->

```cpp
const int* const both{&value};
```
