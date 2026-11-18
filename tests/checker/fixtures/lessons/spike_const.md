# Fixture: const i wskazniki

Techniczny fixture prototypu checkera. To nie jest lekcja kursu.

Dozwolone operacje kompilują się.

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

Zapis przez wskaźnik do stałej jest błędem.

<!-- compile_fail: write_through_reader at=4:13 error=not assignable -->

```cpp
int main() {
    int value{1};
    const int* reader{&value};
    *reader = 2;
    return value;
}
```

Stałego wskaźnika nie można przestawić.

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

Sam zapis deklaracji, bez programu:

<!-- fragment -->

```cpp
const int* const both{&value};
```
