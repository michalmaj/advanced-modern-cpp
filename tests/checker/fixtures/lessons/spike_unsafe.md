# Fixture: kod niebezpieczny tylko do analizy

Techniczny fixture prototypu checkera. To nie jest lekcja kursu.

Zwrot referencji do zmiennej lokalnej. Sprawdzana jest tylko kompilacja.

<!-- compile_unsafe: dangling_return allow=-Wreturn-stack-address@3 -->

```cpp
const int& pick_local() {
    int local{42};
    return local;
}

int main() {
    return 0;
}
```

Widok na obiekt tymczasowy.

<!-- compile_unsafe: view_of_temporary allow=-Wdangling-gsl@5 -->

```cpp
#include <string>
#include <string_view>

int main() {
    std::string_view view = std::string("temporary text");
    return view.empty() ? 1 : 0;
}
```

Sentinel: uruchomienie zostawiłoby plik. Po sprawdzeniu pliku nie może być.

<!-- compile_unsafe: sentinel_program -->

```cpp
#include <fstream>

int main() {
    std::ofstream trace{"SENTINEL-compile_unsafe-was-executed.txt"};
    trace << "this program must never be run by the checker\n";
}
```
